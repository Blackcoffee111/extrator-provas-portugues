"""Módulo 7 — Upload de questões para Supabase (schema v2).

Fluxo completo:
  1. Carrega questões de ``questoes_final.json``
  2. Faz upload de imagens locais → Supabase Storage (bucket questoes-media)
  3. Resolve (get-or-create) registos nas tabelas auxiliares:
       materias → fontes → topicos → contextos
  4. Upsert das questões na tabela ``questoes`` com os FKs resolvidos

Chave de unicidade: ``UNIQUE(fonte_id, COALESCE(grupo,''), id_item)``
Re-runs são idempotentes.
"""

from __future__ import annotations

import json
import mimetypes
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings
from .schemas import Question, load_questions


# ── Erro customizado ──────────────────────────────────────────────────────────

class SupabaseError(Exception):
    def __init__(self, status: int, body: str, url: str):
        self.status = status
        self.body   = body
        self.url    = url
        super().__init__(f"HTTP {status} em {url}: {body[:300]}")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: Any = None,
    timeout: int = 30,
) -> dict | list:
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req  = urllib.request.Request(
        url=url, data=data, method=method,
        headers={"Content-Type": "application/json; charset=utf-8", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
        return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SupabaseError(exc.code, body, url) from exc


def _upload_binary(url: str, headers: dict[str, str], file_path: Path) -> None:
    ct  = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    req = urllib.request.Request(
        url=url, data=file_path.read_bytes(),
        headers={"Content-Type": ct, **headers}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120):
            pass
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        is_dup = exc.code == 409 or (exc.code == 400 and "Duplicate" in body)
        if is_dup:
            req_put = urllib.request.Request(
                url=url, data=file_path.read_bytes(),
                headers={"Content-Type": ct, **headers}, method="PUT",
            )
            with urllib.request.urlopen(req_put, timeout=120):
                pass
        else:
            raise SupabaseError(exc.code, body, url) from exc


def _sb_headers(settings: Settings) -> dict[str, str]:
    return {
        "apikey":        settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
    }


# ── Utilitários ───────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Converte texto em slug URL-safe: "Transformações de Funções" → "transformacoes-de-funcoes"."""
    text = text.lower().strip()
    # Substituições de caracteres acentuados comuns (PT)
    for src, dst in [
        ("ã","a"),("â","a"),("à","a"),("á","a"),("ä","a"),
        ("ê","e"),("é","e"),("è","e"),("ë","e"),
        ("î","i"),("í","i"),("ï","i"),
        ("ô","o"),("ó","o"),("õ","o"),("ö","o"),
        ("ú","u"),("û","u"),("ü","u"),
        ("ç","c"),("ñ","n"),
    ]:
        text = text.replace(src, dst)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _parse_fonte(fonte: str) -> dict[str, Any]:
    """Extrai metadata de uma string de fonte legível.

    Exemplo: "Exame Nacional, Matemática A, 1.ª Fase, 2024"
    → {tipo: "Exame Nacional", materia: "Matemática A", fase: "1.ª Fase", ano: 2024}
    """
    parts   = [p.strip() for p in fonte.split(",")]
    ano_m   = re.search(r"\b(19|20)\d{2}\b", fonte)
    fase_m  = re.search(r"\d+\.ª\s*(?:Fase|fase)", fonte)
    tipo    = parts[0] if parts else "Outro"

    # Matéria: parte que não tem dígitos de ano nem padrão de fase
    materia = ""
    for part in parts[1:]:
        if not re.search(r"\b\d{4}\b|\d+\.ª", part):
            materia = part.strip()
            break

    return {
        "tipo":    tipo,
        "materia": materia,
        "ano":     int(ano_m.group()) if ano_m else None,
        "fase":    fase_m.group()     if fase_m else None,
    }


# ── Resolução de tabelas auxiliares (get-or-create) ──────────────────────────

def _get_or_create_materia(
    settings: Settings, headers: dict[str, str], nome: str
) -> str:
    """Retorna o id de uma matéria, criando-a se não existir."""
    if not nome:
        nome = "Desconhecido"
    codigo = _slugify(nome)
    url = (f"{settings.supabase_url}/rest/v1/materias"
           f"?codigo=eq.{codigo}&select=id")
    rows = _request("GET", url, headers)
    if rows:
        return rows[0]["id"]

    result = _request(
        "POST", f"{settings.supabase_url}/rest/v1/materias",
        {**headers, "Prefer": "return=representation"},
        {"codigo": codigo, "nome": nome},
    )
    return (result[0] if isinstance(result, list) else result)["id"]


def _get_or_create_fonte(
    settings: Settings,
    headers: dict[str, str],
    descricao: str,
    materia_id: str,
) -> str:
    """Retorna o id de uma fonte, criando-a se não existir."""
    url = (f"{settings.supabase_url}/rest/v1/fontes"
           f"?descricao=eq.{urllib.parse.quote(descricao)}&select=id")
    rows = _request("GET", url, headers)
    if rows:
        return rows[0]["id"]

    meta   = _parse_fonte(descricao)
    result = _request(
        "POST", f"{settings.supabase_url}/rest/v1/fontes",
        {**headers, "Prefer": "return=representation"},
        {
            "materia_id":  materia_id,
            "descricao":   descricao,
            "tipo":        meta["tipo"],
            "ano":         meta["ano"],
            "fase":        meta["fase"],
        },
    )
    return (result[0] if isinstance(result, list) else result)["id"]


def _get_or_create_topico(
    settings: Settings,
    headers: dict[str, str],
    tema: str,
    subtema: str,
    materia_id: str,
) -> str | None:
    """Retorna o id do topico (subtema se existir, senão tema), criando os registos."""
    if not tema:
        return None

    tema_slug = _slugify(tema)

    # Nível 1 — tema
    url = (f"{settings.supabase_url}/rest/v1/topicos"
           f"?materia_id=eq.{materia_id}"
           f"&slug=eq.{urllib.parse.quote(tema_slug)}"
           f"&nivel=eq.1&select=id")
    rows = _request("GET", url, headers)
    if rows:
        tema_id = rows[0]["id"]
    else:
        try:
            result = _request(
                "POST", f"{settings.supabase_url}/rest/v1/topicos",
                {**headers, "Prefer": "return=representation"},
                {"materia_id": materia_id, "nome": tema,
                 "slug": tema_slug, "nivel": 1},
            )
            tema_id = (result[0] if isinstance(result, list) else result)["id"]
        except SupabaseError as exc:
            if exc.status != 409:
                raise
            # Slug já existe para esta materia (possivelmente noutro nivel).
            # O constraint é (materia_id, slug) sem nivel — procurar sem filtro de nivel.
            url_any = (f"{settings.supabase_url}/rest/v1/topicos"
                       f"?materia_id=eq.{materia_id}"
                       f"&slug=eq.{urllib.parse.quote(tema_slug)}"
                       f"&select=id")
            rows2 = _request("GET", url_any, headers)
            tema_id = rows2[0]["id"]

    if not subtema:
        return tema_id

    # Nível 2 — subtema
    sub_slug = _slugify(subtema)
    url2 = (f"{settings.supabase_url}/rest/v1/topicos"
            f"?materia_id=eq.{materia_id}"
            f"&slug=eq.{urllib.parse.quote(sub_slug)}"
            f"&nivel=eq.2&select=id")
    rows = _request("GET", url2, headers)
    if rows:
        return rows[0]["id"]

    try:
        result = _request(
            "POST", f"{settings.supabase_url}/rest/v1/topicos",
            {**headers, "Prefer": "return=representation"},
            {"materia_id": materia_id, "nome": subtema,
             "slug": sub_slug, "pai_id": tema_id, "nivel": 2},
        )
        return (result[0] if isinstance(result, list) else result)["id"]
    except SupabaseError as exc:
        if exc.status != 409:
            raise
        # Mesmo raciocínio: constraint (materia_id, slug) sem nivel
        url2_any = (f"{settings.supabase_url}/rest/v1/topicos"
                    f"?materia_id=eq.{materia_id}"
                    f"&slug=eq.{urllib.parse.quote(sub_slug)}"
                    f"&select=id")
        rows2 = _request("GET", url2_any, headers)
        return rows2[0]["id"]


def _extract_notas_rodape(observacoes: list[str]) -> list[dict]:
    """Extrai notas_rodape guardadas em observacoes como 'notas_rodape: [...]'."""
    for obs in (observacoes or []):
        if obs.startswith("notas_rodape:"):
            try:
                return json.loads(obs[len("notas_rodape:"):].strip())
            except (json.JSONDecodeError, ValueError):
                pass
    return []


def _upsert_contexto(
    settings: Settings,
    headers: dict[str, str],
    q: Question,
    fonte_id: str,
    url_map: dict[str, str],
) -> str:
    """Cria ou actualiza um contexto a partir de um item context_stem."""
    imagens_json = _build_imagens_jsonb(q, url_map)
    notas_rodape = _extract_notas_rodape(q.observacoes)
    url = (f"{settings.supabase_url}/rest/v1/contextos"
           f"?on_conflict=fonte_id,id_item_original")
    result = _request(
        "POST", url,
        {**headers, "Prefer": "return=representation,resolution=merge-duplicates"},
        {
            "fonte_id":         fonte_id,
            "texto":            q.enunciado or "",
            "imagens":          imagens_json,
            "grupo":            q.grupo or "",
            "id_item_original": q.id_item,
            "pagina_origem":    q.pagina_origem,
            "notas_rodape":     notas_rodape or [],
        },
    )
    return (result[0] if isinstance(result, list) else result)["id"]


# ── Imagens ───────────────────────────────────────────────────────────────────

def _build_imagens_jsonb(q: Question, url_map: dict[str, str]) -> list[dict]:
    """Converte a lista de imagens (URLs ou paths locais) em objectos jsonb com metadata."""
    result = []
    desc_map = q.descricoes_imagens or {}
    for img_ref in (q.imagens or []):
        url = url_map.get(img_ref, img_ref)
        # Tentar encontrar descrição por path local ou por URL
        descricao = desc_map.get(img_ref) or desc_map.get(url) or ""
        alt = Path(img_ref).stem if not img_ref.startswith("http") else url.split("/")[-1].split(".")[0]
        result.append({"url": url, "descricao": descricao, "alt": alt})
    return result


def _upload_images(
    settings: Settings,
    questions: list[Question],
    base_dir: Path,
    headers: dict[str, str],
    dry_run: bool = False,
) -> dict[str, str]:
    """Faz upload de todas as imagens e retorna mapa path_local → URL_pública."""
    uploaded: dict[str, str] = {}
    all_refs: set[str] = set()
    for q in questions:
        all_refs.update(q.imagens or [])
        all_refs.update(q.imagens_contexto or [])

    for ref in sorted(all_refs):
        if ref.startswith("http://") or ref.startswith("https://"):
            continue
        local = (base_dir / ref).resolve()
        if not local.exists():
            continue

        object_name = f"{base_dir.name}/{local.name}"
        encoded     = urllib.parse.quote(object_name, safe="/")
        public_url  = (f"{settings.supabase_url}/storage/v1/object/public/"
                       f"{settings.supabase_bucket}/{encoded}")

        if dry_run:
            uploaded[ref] = public_url
            continue

        upload_url = (f"{settings.supabase_url}/storage/v1/object/"
                      f"{settings.supabase_bucket}/{encoded}")
        _upload_binary(upload_url, headers, local)
        uploaded[ref] = public_url

    return uploaded


# ── Conversão Question → row DB ───────────────────────────────────────────────

def _question_to_row(
    q: Question,
    fonte_id: str,
    contexto_id: str | None,
    topico_id: str | None,
    url_map: dict[str, str],
) -> dict[str, Any]:
    """Converte um Question para um dict compatível com a tabela questoes (v2)."""
    return {
        # FKs
        "fonte_id":    fonte_id,
        "contexto_id": contexto_id,
        "topico_id":   topico_id,
        # Identificação
        "id_item":         q.id_item,
        "grupo":           q.grupo or "",
        "numero_questao":  q.numero_questao,
        "subitem":         q.subitem,
        # Conteúdo
        "tipo_item":   q.tipo_item,
        "enunciado":   q.enunciado or "",
        "alternativas": [
            {"letra": a.letra, "texto": a.texto}
            for a in (q.alternativas or [])
        ],
        "imagens": _build_imagens_jsonb(q, url_map),
        # Resposta / CC
        "resposta_correta":        q.resposta_correta,
        "solucao":                 q.solucao or "",
        "criterios_parciais":      q.criterios_parciais or [],
        "resolucoes_alternativas": q.resolucoes_alternativas or [],
        # Classificação (desnormalizado)
        "materia":       q.materia or "",
        "tema":          q.tema or "",
        "subtema":       q.subtema or "",
        "tags":          q.tags or [],
        "descricao_breve": q.descricao_breve or "",
        # Legível desnormalizado
        "fonte":         q.fonte or "",
        # Campos PT (nullable — ignorados para Matemática A)
        "pool_opcional":            q.pool_opcional or None,
        "palavras_min":             q.palavras_min,
        "palavras_max":             q.palavras_max,
        "linhas_referenciadas":     q.linhas_referenciadas or [],
        "parametros_classificacao": q.parametros_classificacao or [],
        # Metadados
        "pagina_origem": q.pagina_origem,
        "status":        q.status or "approved",
        "observacoes":   q.observacoes or [],
    }


def _upsert_rows(
    settings: Settings,
    rows: list[dict[str, Any]],
    headers: dict[str, str],
) -> list[dict]:
    if not rows:
        return []
    url = (f"{settings.supabase_url}/rest/v1/{settings.supabase_table}"
           f"?on_conflict=fonte_id,grupo,id_item")
    result = _request(
        "POST", url,
        {**headers, "Prefer": "return=representation,resolution=merge-duplicates"},
        rows,
    )
    return result if isinstance(result, list) else [result]


# ── Resultado ─────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class UploadSummary:
    uploaded_images: dict[str, str] = field(default_factory=dict)
    upserted_rows:   int = 0
    skipped_rows:    int = 0
    errors:          list[str] = field(default_factory=list)
    dry_run:         bool = False


# ── Função principal ──────────────────────────────────────────────────────────

def upload_to_supabase(
    settings: Settings,
    final_json_path: Path,
    *,
    dry_run: bool = False,
) -> UploadSummary:
    """Faz upload de questões finais para Supabase (schema v2).

    Context stems (tipo_item='context_stem') são inseridos na tabela
    ``contextos``; todas as outras questões vão para ``questoes``.
    """
    final_json_path = final_json_path.resolve()
    summary = UploadSummary(dry_run=dry_run)

    questions = load_questions(final_json_path)
    if not questions:
        summary.errors.append("Nenhuma questão encontrada.")
        return summary

    # Checagem de categorização — bloqueia upload se houver questões sem tema
    sem_cat = [
        q.id_item for q in questions
        if q.tipo_item not in {"context_stem"}
        and (not q.tema or q.tema.strip().lower() in {"", "por categorizar"})
    ]
    if sem_cat:
        msg = f"Upload bloqueado: {len(sem_cat)} questão(ões) sem categorização: {sem_cat}. Categorize antes de fazer upload."
        print(f"[upload] ❌ {msg}")
        summary.errors.append(msg)
        return summary

    if not settings.supabase_url or not settings.supabase_key:
        summary.errors.append("SUPABASE_URL / SUPABASE_KEY não configurados.")
        summary.dry_run = True
        return summary

    headers  = _sb_headers(settings)
    base_dir = final_json_path.parent

    # ── 0. Backup pré-upload (ficheiros locais do workspace) ──────────────────
    if not dry_run:
        try:
            from .module_backup import backup_workspace_files  # noqa: PLC0415
            backup_workspace_files(base_dir)
        except Exception as exc:
            print(f"[upload] ⚠️  Backup pré-upload falhou (upload continua): {exc}")

    # ── 1. Upload de imagens ──────────────────────────────────────────────────
    print(f"[upload] {'[DRY-RUN] ' if dry_run else ''}A enviar imagens…")
    try:
        url_map = _upload_images(settings, questions, base_dir, headers, dry_run=dry_run)
        summary.uploaded_images = url_map
        print(f"[upload] ✅ {len(url_map)} imagens {'mapeadas' if dry_run else 'enviadas'}.")
    except SupabaseError as exc:
        summary.errors.append(f"Erro imagens: {exc}")
        url_map = {}
        print(f"[upload] ❌ {exc}")

    # ── 2. Resolver matéria e fonte ───────────────────────────────────────────
    # Todas as questões de um ficheiro partilham a mesma fonte
    fonte_str  = questions[0].fonte if questions else ""
    materia_str = questions[0].materia if questions else ""
    if not materia_str:
        materia_str = _parse_fonte(fonte_str).get("materia") or "Desconhecido"

    if dry_run:
        fonte_id   = "dry-run-fonte-id"
        materia_id = "dry-run-materia-id"
        print(f"[upload] [DRY-RUN] Fonte: {fonte_str!r}")
    else:
        print(f"[upload] A resolver matéria: {materia_str!r}")
        materia_id = _get_or_create_materia(settings, headers, materia_str)
        print(f"[upload] A resolver fonte: {fonte_str!r}")
        fonte_id   = _get_or_create_fonte(settings, headers, fonte_str, materia_id)

    # ── 3. Criar contextos a partir de context_stem ───────────────────────────
    # Mapa id_item → contexto_id, para os sub-items consultarem
    contexto_map: dict[str, str] = {}
    for q in questions:
        if q.tipo_item != "context_stem":
            continue
        if dry_run:
            contexto_map[q.id_item] = f"dry-run-ctx-{q.id_item}"
            continue
        try:
            ctx_id = _upsert_contexto(settings, headers, q, fonte_id, url_map)
            contexto_map[q.id_item] = ctx_id
        except SupabaseError as exc:
            summary.errors.append(f"Contexto {q.id_item}: {exc}")
            print(f"[upload] ❌ Contexto {q.id_item}: {exc}")

    print(f"[upload] {len(contexto_map)} contextos resolvidos.")

    # ── 4. Preparar rows de questões ──────────────────────────────────────────
    rows: list[dict[str, Any]] = []
    for q in questions:
        if q.tipo_item == "context_stem":
            continue  # já tratado em contextos

        # Descobrir contexto_id: o pai é o prefixo antes do primeiro ponto.
        # Priorizar id_item (lida com "II-1.1" → "II-1" e "1.1" → "1");
        # fallback para numero_principal em formatos antigos sem grupo;
        # fallback PT: contexto de grupo ("<grupo>-ctx") para provas de Português.
        contexto_id: str | None = None
        if "." in q.id_item:
            pai = q.id_item.split(".")[0]
            contexto_id = contexto_map.get(pai)
        if contexto_id is None and q.numero_principal is not None:
            contexto_id = contexto_map.get(str(q.numero_principal))
        if contexto_id is None and q.grupo:
            contexto_id = contexto_map.get(f"{q.grupo}-ctx")

        # Resolver tópico
        topico_id: str | None = None
        if not dry_run and q.tema:
            try:
                topico_id = _get_or_create_topico(
                    settings, headers, q.tema, q.subtema, materia_id
                )
            except SupabaseError as exc:
                summary.errors.append(f"Tópico {q.tema}/{q.subtema}: {exc}")

        try:
            row = _question_to_row(q, fonte_id, contexto_id, topico_id, url_map)
            rows.append(row)
        except Exception as exc:
            summary.errors.append(f"Converter {q.id_item}: {exc}")
            summary.skipped_rows += 1

    print(f"[upload] {len(rows)} questões preparadas ({summary.skipped_rows} ignoradas).")

    # ── 5. Dry-run: preview sem enviar ────────────────────────────────────────
    if dry_run:
        summary.upserted_rows = len(rows)
        preview = base_dir / "upload_preview.json"
        preview.write_text(
            json.dumps(rows[:3], indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[upload] [DRY-RUN] {len(rows)} questões seriam enviadas → preview: {preview}")
        return summary

    # ── 6. Upsert ─────────────────────────────────────────────────────────────
    print(f"[upload] A enviar {len(rows)} questões…")
    try:
        result = _upsert_rows(settings, rows, headers)
        summary.upserted_rows = len(result) if isinstance(result, list) else len(rows)
        print(f"[upload] ✅ {summary.upserted_rows} questões inseridas/actualizadas.")
    except SupabaseError as exc:
        summary.errors.append(f"Upsert batch: {exc}")
        print(f"[upload] ❌ Batch falhou — a tentar uma a uma…")
        ok = 0
        for row in rows:
            try:
                _upsert_rows(settings, [row], headers)
                ok += 1
            except SupabaseError as row_exc:
                iid = row.get("id_item", "?")
                summary.errors.append(f"Item {iid}: {row_exc}")
                print(f"[upload]   ❌ {iid}: HTTP {row_exc.status}")
        summary.upserted_rows = ok
        if ok:
            print(f"[upload] ✅ {ok}/{len(rows)} questões inseridas individualmente.")

    if summary.errors:
        print(f"[upload] ⚠️  {len(summary.errors)} erros registados.")
    else:
        print(f"[upload] 🎉 Completo — {summary.upserted_rows} questões no Supabase!")

    # ── 7. Backup automático após upload bem-sucedido ─────────────────────────
    if not dry_run and not summary.errors:
        print("[upload] A actualizar backup local…")
        try:
            from .module_backup import run_backup  # noqa: PLC0415
            run_backup(settings)
        except Exception as exc:
            print(f"[upload] ⚠️  Backup falhou (dados já estão no Supabase): {exc}")

    return summary
