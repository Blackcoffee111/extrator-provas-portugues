"""MCP Server — Exames Nacionais Pipeline (P3: superfície reduzida a 7 tools).

Ferramentas expostas:
  list_workspaces()           — lista workspaces e estado resumido de cada um
  workspace_status(workspace) — estado detalhado + próxima acção sugerida
  run_stage(workspace, stage) — executa um estágio do pipeline
  run_review(workspace)       — abre preview interactivo para revisão humana
  run_fix_question(...)       — correcção de questão via overlay (não destrutivo)
  run_fix_cc(...)             — correcção de critérios CC via overlay (não destrutivo)
  get_cc_context(ws_cc, id)   — texto_original de um critério sem ler o JSON inteiro

Stages de run_stage:
  extract   — OCR (MinerU) + cotações + estruturação
  validate  — micro-lint interno + validação heurística
  cc        — critérios CC-VD: 1ª chamada → cc_extract; 2ª chamada → cc_validate
  merge     — cc_merge + abre preview
  upload    — upload Supabase + backup automático
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import overlay as overlay_mod
from .module_categorize import check_all_categorized
from .workspace_state import WorkspaceStage

# ── Configuração ──────────────────────────────────────────────────────────────

_REPO_DIR = Path(os.environ.get("PIPELINE_ROOT", Path(__file__).parent.parent.parent))
_WORKSPACE_DIR = _REPO_DIR / "workspace"
_PYTHON = os.environ.get("PIPELINE_PYTHON", "/opt/homebrew/bin/python3.11")
_PKG = "exames_pipeline.cli"

mcp = FastMCP(
    "Exames Nacionais Pipeline",
    instructions=(
        "SEQUÊNCIA LINEAR OBRIGATÓRIA — nunca saltar nem paralelizar passos:\n"
        "    1. run_stage(extract, pdf_path='...') ← SEMPRE PRIMEIRO; pré-processa + tenta MinerU auto\n"
        "       Se retornar '⚠️ MinerU falhou': pedir ao utilizador para correr o comando exacto impresso\n"
        "       e depois chamar run_stage(extract) SEM pdf_path — normaliza output automaticamente.\n"
        "    2. AGENTE revê prova.md (Read + Edit)\n"
        "    3. AGENTE revê questoes_review.json (reviewed:true + categorização em cada item)\n"
        "    4. run_stage(validate)  ← só avança quando TODOS os itens tiverem reviewed:true\n"
        "    5. run_stage(cc, pdf_cc_path='...') ← tenta MinerU CC-VD auto; mesmo fallback acima\n"
        "    6. AGENTE revê criterios_review.json + criterios_ocr_flags.json\n"
        "       (para OCR-SUSPECT: usar get_cc_context(); documentar em OCR-RESOLVED: ou OCR-FALSE-POSITIVE:)\n"
        "    7. run_stage(cc)  ← 2ª chamada (cc_validate)\n"
        "    8. run_stage(merge)\n"
        "    9. run_review  ← humano aprova no browser\n"
        "   10. run_stage(upload)\n"
        "Em dúvida: workspace_status(). Correcções pós-merge: run_fix_question() / run_fix_cc() — não destrutivos.\n"
        "NUNCA pedir ao utilizador para correr MinerU antes de tentar run_stage com pdf_path.\n"
        "NUNCA pedir cp manual de prova.md ou images/ — run_stage normaliza o output automaticamente."
    ),
)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _run(args: list[str], cwd: Path | None = None, timeout: int = 300) -> dict[str, Any]:
    """Corre um subcomando do pipeline e devolve {ok, stdout, stderr, returncode}."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_REPO_DIR / "src")
    env["PIPELINE_ROOT"] = str(_REPO_DIR)
    cmd = [_PYTHON, "-m", _PKG] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd or _REPO_DIR),
            env=env,
            timeout=timeout,
        )
        return {
            "ok":         result.returncode == 0,
            "stdout":     result.stdout.strip(),
            "stderr":     result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"Timeout ({timeout}s)", "returncode": -1}
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc), "returncode": -1}


def _workspace_path(workspace_name: str) -> Path:
    return _WORKSPACE_DIR / workspace_name


def _file_exists(workspace: str, filename: str) -> bool:
    return (_workspace_path(workspace) / filename).exists()


def _count_json(workspace: str, filename: str) -> int | None:
    path = _workspace_path(workspace) / filename
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return len(data) if isinstance(data, list) else None
    except Exception:
        return None


_UPLOAD_RESULTADO_RE = re.compile(
    r"\[resultado\]\s+status=\S+\s+imagens=\d+\s+"
    r"upserted=(?P<upserted>\d+)\s+"
    r"skipped=(?P<skipped>\d+)\s+"
    r"erros=(?P<erros>\d+)"
)


def _parse_upload_resultado(stdout: str) -> tuple[int | None, int | None, int | None]:
    """Extrai (upserted, skipped, erros) da linha [resultado] do upload CLI.

    Devolve (None, None, None) se a linha não for encontrada (formato mudou
    ou upload falhou antes de chegar ao print final). Quando isto acontece,
    o caller trata como falha implícita.
    """
    m = _UPLOAD_RESULTADO_RE.search(stdout or "")
    if not m:
        return None, None, None
    return (
        int(m.group("upserted")),
        int(m.group("skipped")),
        int(m.group("erros")),
    )


# Campos do overlay cuja edição implica intenção humana de ENVIAR o item ao
# Supabase. Se algum destes for editado num item órfão (que não existe em
# final.json), o upload deve BLOQUEAR — não basta avisar — porque o trabalho
# de revisão humana seria silenciosamente descartado.
_OVERLAY_FIELDS_CRITICOS = {
    "enunciado", "alternativas", "resposta_correta", "respostas_corretas",
    "solucao", "criterios_parciais", "resolucoes_alternativas",
    "tema", "subtema", "descricao_breve", "tags", "imagens",
    "palavras_min", "palavras_max", "linhas_referenciadas",
    "parametros_classificacao", "pool_opcional",
}


def _orphan_overlay_with_content(ws_dir: Path, orphans: list[str]) -> dict[str, list[str]]:
    """Devolve {id_item: [campo, ...]} para órfãos que editam campos críticos.

    Vazio se overlay órfão só toca metadata (status, observacoes auto, etc.).
    """
    if not orphans:
        return {}
    overlay_path = ws_dir / "correcoes_humanas.json"
    if not overlay_path.exists():
        return {}
    try:
        ov = json.loads(overlay_path.read_text(encoding="utf-8"))
        items = ov.get("items", {}) if isinstance(ov, dict) else {}
    except Exception:
        return {}

    result: dict[str, list[str]] = {}
    for iid in orphans:
        entry = items.get(iid, {})
        if not isinstance(entry, dict):
            continue
        criticos = sorted(set(entry.keys()) & _OVERLAY_FIELDS_CRITICOS)
        if criticos:
            result[iid] = criticos
    return result


def _excluded_items_summary(workspace: str) -> dict[str, Any]:
    """Recolhe IDs excluídos ao longo do pipeline (validate + merge + sem rastro).

    Devolve um dict com:
      - validation_errors: list[str]  (IDs em questoes_com_erro.json)
      - merge_pendente:    list[str]  (IDs em questoes_merge_pendente.json)
      - silent_drop:       list[str]  (revistos mas não em final.json
                                       e SEM rastro em com_erro/pendente —
                                       provavelmente alguém apagou os ficheiros
                                       intermédios. Bug do tipo F1/F2 2011.)
      - reviewed_total:    int        (total em questoes_review.json)
      - final_total:       int        (total em questoes_final.json)
      - has_exclusions:    bool       (True se QUALQUER exclusão a reportar)
    """
    ws_dir = _workspace_path(workspace)

    def _ids(filename: str) -> list[str]:
        path = ws_dir / filename
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [
            q.get("id_item") or str(q.get("numero_questao") or "?")
            for q in data
            if isinstance(q, dict)
        ]

    val_err = _ids("questoes_com_erro.json")
    merge_pend = _ids("questoes_merge_pendente.json")
    review_ids = _ids("questoes_review.json")
    final_ids = _ids("questoes_final.json")

    # Silent drop: revistos que NÃO chegaram ao final E não estão noutro
    # ficheiro de exclusão. Detecta o cenário em que com_erro/pendente foi
    # apagado, ou em que o final foi materializado a partir dum aprovado
    # antigo (sem alguns IDs que existiam em review).
    # Só ativa se houver final.json — se ainda não houve merge, não há
    # significado em comparar.
    silent_drop: list[str] = []
    if final_ids:  # merge já correu
        known_excl = set(val_err) | set(merge_pend) | set(final_ids)
        silent_drop = sorted(set(review_ids) - known_excl)

    return {
        "validation_errors": val_err,
        "merge_pendente":    merge_pend,
        "silent_drop":       silent_drop,
        "reviewed_total":    len(review_ids),
        "final_total":       len(final_ids),
        "has_exclusions":    bool(val_err) or bool(merge_pend) or bool(silent_drop),
    }


def _format_exclusions_warning(summary: dict[str, Any]) -> str:
    """Formata mensagem de aviso destacado sobre itens excluídos.

    Devolve string vazia se não há exclusões.
    """
    if not summary["has_exclusions"]:
        return ""

    val_err = summary["validation_errors"]
    merge_pend = summary["merge_pendente"]
    silent = summary.get("silent_drop", [])
    parts: list[str] = []
    parts.append("⚠️  ITENS EXCLUÍDOS DO UPLOAD:")
    if val_err:
        ids_fmt = ", ".join(val_err)
        parts.append(
            f"  • {len(val_err)} rejeitado(s) no validate "
            f"→ questoes_com_erro.json: {ids_fmt}"
        )
    if merge_pend:
        ids_fmt = ", ".join(merge_pend)
        parts.append(
            f"  • {len(merge_pend)} sem critério no merge "
            f"→ questoes_merge_pendente.json: {ids_fmt}"
        )
    if silent:
        ids_fmt = ", ".join(silent)
        parts.append(
            f"  🔥 {len(silent)} SUMIDO(S) SEM RASTRO — revistos mas não em "
            f"final.json e sem registo em com_erro/pendente: {ids_fmt}\n"
            f"     (provavelmente os ficheiros de exclusão foram apagados ou "
            f"o final.json é antigo. Re-correr validate+merge.)"
        )
    parts.append(
        f"  Revistos: {summary['reviewed_total']}  ·  "
        f"a enviar: {summary['final_total']}  ·  "
        f"excluídos: {len(val_err) + len(merge_pend) + len(silent)}"
    )
    return "\n".join(parts) + "\n"


def _count_reviewed(workspace: str) -> tuple[int, int] | None:
    """Devolve (reviewed, total). Prefere questoes_review.json; cai em questoes_raw.json."""
    ws_dir = _workspace_path(workspace)
    for fname in ("questoes_review.json", "questoes_raw.json"):
        path = ws_dir / fname
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
            total = len(data)
            reviewed = sum(1 for q in data if isinstance(q, dict) and q.get("reviewed"))
            return reviewed, total
        except Exception:
            continue
    return None


def _merge_review_meta(workspace: str) -> str | None:
    """Merge questoes_review.json + questoes_meta.json → questoes_raw.json antes do validate.

    Devolve mensagem de erro ou None se bem-sucedido.
    Se questoes_review.json não existir (workspace antigo), não faz nada (None).
    """
    ws_dir = _workspace_path(workspace)
    review_path = ws_dir / "questoes_review.json"
    meta_path   = ws_dir / "questoes_meta.json"

    if not review_path.exists():
        return None  # workspace antigo — questoes_raw.json já está completo

    if not meta_path.exists():
        return f"❌ questoes_meta.json não encontrado em '{workspace}' (ficheiro gerado pelo extract)."

    try:
        review_list: list[dict] = json.loads(review_path.read_text(encoding="utf-8"))
        meta_list:   list[dict] = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"❌ Erro ao ler ficheiros de review/meta: {exc}"

    meta_by_id = {m.get("id_item", ""): m for m in meta_list}
    # Ordem máxima existente no meta, para atribuir valores sequenciais aos itens novos
    _max_ordem = max((m.get("ordem_item") or 0 for m in meta_list), default=0)
    _ITEM_ID_RE = re.compile(r"^(?:[IVX]+-)?(?P<main>\d{1,3})(?:\.(?P<sub>\d{1,2}))?$")

    # Inferir matéria a partir das entradas existentes (este é o pipeline PT,
    # mas mantém-se a inferência caso o meta venha com "Português" canónico).
    _materia_default = (
        meta_list[0].get("materia") if meta_list and meta_list[0].get("materia")
        else "Português"
    )

    def _meta_fallback(id_: str, ordem: int) -> dict:
        """Gera entrada de meta mínima para itens ausentes do questoes_meta.json."""
        mat = _ITEM_ID_RE.match(id_)
        main = int(mat.group("main")) if mat else 0
        sub  = mat.group("sub") if mat else None
        return {
            "id_item": id_,
            "numero_questao": main,
            "ordem_item": ordem,
            "numero_principal": main,
            "subitem": sub,
            "materia": _materia_default,
            "imagens_contexto": [],
            "pagina_origem": None,
            "fonte": "",
            "status": "draft",
            "texto_original": "",
            "source_span": None,
            "grupo_ids": [id_],
            "descricoes_imagens": {},
            "criterios_parciais": [],
            "resolucoes_alternativas": [],
        }

    # ── Gate anti-renumeração ────────────────────────────────────────────────
    # Se o agente renumerou IDs em questoes_review.json (ex.: corrigiu uma
    # extração defeituosa onde I-A-2 estava marcado como I-A-1), os IDs em
    # review e meta desalinham-se: review tem IDs novos que não existem em
    # meta, e meta tem órfãos que já não estão em review. O merge actual junta
    # review.enunciado novo com meta.texto_original/source_span/ordem antigo →
    # mistura silenciosa de conteúdos, validate aceita, agente vê preview com
    # questão errada associada à pergunta certa.
    #
    # Itens novos legítimos (review tem IDs ausentes do meta, mas meta não
    # tem órfãos) continuam a passar — o `_meta_fallback` cobre esse caso.
    review_ids = {r.get("id_item", "") for r in review_list if r.get("id_item")}
    meta_ids = {m.get("id_item", "") for m in meta_list if m.get("id_item")}
    new_in_review = review_ids - meta_ids
    orphan_in_meta = meta_ids - review_ids
    if new_in_review and orphan_in_meta:
        return (
            "❌ IDs divergentes entre questoes_review.json e questoes_meta.json — "
            "provável renumeração:\n"
            f"  Novos no review (ausentes no meta): {sorted(new_in_review)}\n"
            f"  Órfãos no meta (apagados do review): {sorted(orphan_in_meta)}\n\n"
            "  O merge usaria metadados desalinhados (texto_original, source_span,\n"
            "  ordem_item, página) com o enunciado novo — produzindo questoes_raw\n"
            "  com pares review↔meta misturados.\n\n"
            "  Acções:\n"
            f"    1. Re-extrair (regenera o meta a partir do prova.md corrigido):\n"
            f"       run_stage(workspace='{workspace}', stage='extract', force=True)\n"
            "       Categorizações em review.json têm de ser re-aplicadas.\n"
            "    2. OU alinhar manualmente os IDs em questoes_meta.json para\n"
            "       coincidirem com review.json antes de validar."
        )

    merged = []
    for r in review_list:
        id_ = r.get("id_item", "")
        if id_ in meta_by_id:
            m = meta_by_id[id_]
        else:
            _max_ordem += 1
            m = _meta_fallback(id_, _max_ordem)
        merged.append({**m, **r})

    raw_path = ws_dir / "questoes_raw.json"
    try:
        raw_path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:
        return f"❌ Erro ao gravar questoes_raw.json: {exc}"

    return None


# Campos omitidos em criterios_review.json (ver cc_extract._REVIEW_EXCLUDED).
# Têm de ser preservados a partir de criterios_raw.json no merge — o agente
# nunca os edita.
_CRITERIOS_REVIEW_EXCLUDED = {"texto_original", "imagens", "fonte"}


def _merge_criterios_review(workspace_cc: str) -> str | None:
    """Merge criterios_review.json (editado pelo agente) → criterios_raw.json
    antes do cc-validate.

    Análogo ao _merge_review_meta() para o pipeline principal: cc_extract grava
    dois ficheiros (raw completo + review compacto sem texto_original/imagens/
    fonte), o agente edita o review, e o validate lê o raw. Sem este merge as
    edições do agente são silenciosamente ignoradas.

    Devolve mensagem de erro ou None se bem-sucedido. Se criterios_review.json
    não existir (workspace antigo), não faz nada (None).
    """
    ws_dir = _workspace_path(workspace_cc)
    review_path = ws_dir / "criterios_review.json"
    raw_path    = ws_dir / "criterios_raw.json"

    if not review_path.exists():
        return None  # workspace antigo — criterios_raw.json é a única fonte

    if not raw_path.exists():
        return f"❌ criterios_raw.json não encontrado em '{workspace_cc}'."

    try:
        review_list: list[dict] = json.loads(review_path.read_text(encoding="utf-8"))
        raw_list:    list[dict] = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"❌ Erro ao ler ficheiros de review/raw CC: {exc}"

    raw_by_id = {r.get("id_item", ""): r for r in raw_list}

    # Gate anti-renumeração: se o agente reescreveu o review com IDs novos
    # enquanto o raw mantém IDs antigos, o merge produziria entradas
    # desalinhadas (texto_original/imagens/fonte do item antigo emparelhados
    # com solucao/criterios_parciais/resposta_correta de outra questão).
    review_ids = {r.get("id_item", "") for r in review_list if r.get("id_item")}
    raw_ids    = {r.get("id_item", "") for r in raw_list if r.get("id_item")}
    new_in_review = review_ids - raw_ids
    orphan_in_raw = raw_ids - review_ids
    if new_in_review and orphan_in_raw:
        return (
            "❌ IDs divergentes entre criterios_review.json e criterios_raw.json — "
            "provável re-segmentação manual:\n"
            f"  Novos no review (ausentes no raw): {sorted(new_in_review)}\n"
            f"  Órfãos no raw (apagados do review): {sorted(orphan_in_raw)}\n\n"
            "  O merge usaria texto_original/imagens/fonte do raw antigo com a\n"
            "  solução/critérios novos do review — produzindo critérios com\n"
            "  metadados de outra questão.\n\n"
            "  Acções:\n"
            f"    1. Re-extrair (regenera o raw a partir do CC-VD prova.md):\n"
            f"       run_stage(stage='cc', workspace_cc='{workspace_cc}', force=True)\n"
            "       As edições em criterios_review.json têm de ser re-aplicadas.\n"
            "    2. OU alinhar manualmente os IDs em criterios_raw.json para\n"
            "       coincidirem com criterios_review.json antes de validar."
        )

    merged: list[dict] = []
    for r in review_list:
        id_ = r.get("id_item", "")
        base = raw_by_id.get(id_, {})
        # Preservar do raw apenas os campos omitidos no review; tudo o resto
        # vem do review (incluindo reviewed, status, observacoes, solucao…).
        preserved = {
            k: base.get(k, "" if k != "imagens" else [])
            for k in _CRITERIOS_REVIEW_EXCLUDED
        }
        merged.append({**preserved, **r})

    try:
        raw_path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:
        return f"❌ Erro ao gravar criterios_raw.json: {exc}"

    return None


def _find_cc_workspace(workspace: str) -> str | None:
    """Devolve o workspace CC-VD canónico associado ao main, se existir.

    A convenção é determinística:
      EX-Port639-EE-2023_net   →  EX-Port639-EE-2023-CC-VD_net
      EX-MatA635-F1-2024       →  EX-MatA635-F1-2024-CC-VD

    Antes era usada heurística de prefixo comum, que falhava silenciosamente:
    para `EX-Port639-EE-2023_net` o prefixo mais longo era
    `EX-Port639-EE-2024-CC-VD_net` (17 chars — mesma fase, ano errado),
    em vez de devolver None quando o CC-VD do ano correcto ainda não existe.
    """
    if not _WORKSPACE_DIR.exists():
        return None
    if workspace.endswith("_net"):
        canonical = workspace[:-4] + "-CC-VD_net"
        alt = canonical[:-4]  # sem sufixo _net
    else:
        canonical = workspace + "-CC-VD"
        alt = canonical + "_net"
    for candidate in (canonical, alt):
        if (_WORKSPACE_DIR / candidate).is_dir():
            return candidate
    return None


def _workspace_state(ws_dir: Path) -> dict[str, Any]:
    """Devolve o estado resumido de um workspace como dict."""
    name = ws_dir.name
    files = {f.name for f in ws_dir.iterdir()} if ws_dir.exists() else set()
    return {
        "nome":               name,
        "prova_md":           "prova.md" in files,
        "questoes_raw":       _count_json(name, "questoes_raw.json"),
        "questoes_aprovadas": _count_json(name, "questoes_aprovadas.json"),
        "questoes_com_erro":  _count_json(name, "questoes_com_erro.json"),
        "questoes_final":     _count_json(name, "questoes_final.json"),
        "criterios_aprovados":_count_json(name, "criterios_aprovados.json"),
        "upload_done":        _file_exists(name, ".upload_done"),
    }


def _next_action(ws_dir: Path, workspace: str) -> str:
    """Determina a próxima acção sugerida com base no estado actual do workspace."""
    ws = WorkspaceStage(ws_dir)
    stage = ws.stage

    if stage == "uploaded":
        return "✅ Pipeline concluído — questões publicadas no Supabase."

    if stage == "human_approved":
        return f"run_stage(workspace='{workspace}', stage='upload')"

    if stage == "cc_merged":
        return (
            f"run_review(workspace='{workspace}') — abrir preview e aguardar aprovação humana\n"
            f"  Depois: run_stage(workspace='{workspace}', stage='upload')"
        )

    if stage == "validated":
        cc_ws = _find_cc_workspace(workspace)
        if cc_ws:
            cc_dir = _workspace_path(cc_ws)
            cc_st = WorkspaceStage(cc_dir).cc_stage
            if cc_st == "cc_validated":
                return f"run_stage(workspace='{workspace}', stage='merge', workspace_cc='{cc_ws}')"
            if cc_st == "cc_extracted":
                return (
                    f"Rever criterios_raw.json em '{cc_ws}' (reviewed:true em cada item),\n"
                    f"  depois run_stage(workspace='{workspace}', stage='cc', workspace_cc='{cc_ws}')"
                )
            cc_prova = cc_dir / "prova.md"
            if not cc_prova.exists():
                return (
                    f"run_stage(workspace='{workspace}', stage='cc', workspace_cc='{cc_ws}', pdf_cc_path='<CAMINHO-CC-VD.pdf>')\n"
                    f"  (MinerU corre automaticamente; ou omitir pdf_cc_path e correr MinerU manualmente)"
                )
            return f"run_stage(workspace='{workspace}', stage='cc', workspace_cc='{cc_ws}')"
        # Sem CC-VD detectado → ir directamente para revisão + upload
        return (
            f"run_review(workspace='{workspace}') — sem CC-VD detectado, aprovar directamente\n"
            f"  Depois: run_stage(workspace='{workspace}', stage='upload')\n"
            f"  (Se houver CC-VD: run_stage(stage='cc', workspace_cc='<NOME-CC-VD>'))"
        )

    if stage == "extracted":
        rev = _count_reviewed(workspace)
        review_file = "questoes_review.json" if (ws_dir / "questoes_review.json").exists() else "questoes_raw.json"
        if rev:
            reviewed, total = rev
            if reviewed < total:
                return (
                    f"Rever {review_file} ({reviewed}/{total} revistos — "
                    f"{total - reviewed} pendentes: reviewed:true + categorização),\n"
                    f"  depois run_stage(workspace='{workspace}', stage='validate')"
                )
        return f"run_stage(workspace='{workspace}', stage='validate')"

    # fresh
    return f"run_stage(workspace='{workspace}', stage='extract', pdf_path='<CAMINHO_ABSOLUTO_PDF>')"


def _format_result(step: str, result: dict[str, Any]) -> str:
    status = "✅" if result["ok"] else "❌"
    lines  = [f"{status} {step} (código {result['returncode']})"]
    if result["stdout"]:
        lines.append(result["stdout"][-1500:])
    if result["stderr"] and not result["ok"]:
        lines.append(f"STDERR: {result['stderr'][-500:]}")
    return "\n".join(lines)


def _start_preview_background(json_path: Path, cli_cmd: str, port: int) -> str:
    """Inicia servidor de preview em background, matando qualquer processo anterior na porta."""
    import signal
    try:
        pids_out = subprocess.run(
            ["lsof", "-ti", f":{port}"], capture_output=True, text=True
        ).stdout.strip()
        if pids_out:
            for pid in pids_out.split():
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except (ProcessLookupError, ValueError):
                    pass
    except Exception:
        pass
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_REPO_DIR / "src")
    env["PIPELINE_ROOT"] = str(_REPO_DIR)
    subprocess.Popen(
        [_PYTHON, "-m", _PKG, cli_cmd, str(json_path)],
        env=env,
        cwd=str(_REPO_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return f"http://localhost:{port}"


def _snapshot_before_stage(ws_dir: Path, stage: str) -> None:
    """Cria backup dos ficheiros antes de um stage destrutivo (máx 5 por stage)."""
    import shutil
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ws_dir / ".backups" / f"{stage}-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for fname in (
        "questoes_final.json",
        "questoes_aprovadas.json",
        "criterios_aprovados.json",
        "correcoes_humanas.json",
        "questoes_final.approved_snapshot.json",
    ):
        src = ws_dir / fname
        if src.exists():
            shutil.copy2(src, backup_dir / fname)
    # Rotação: manter últimos 5 por stage
    backups_dir = ws_dir / ".backups"
    all_stage = sorted(backups_dir.glob(f"{stage}-*"))
    for old in all_stage[:-5]:
        shutil.rmtree(old, ignore_errors=True)


def _overlay_gate_msg(ws_dir: Path) -> str:
    """Mensagem informativa se houver overlay activo. Não bloqueia."""
    summary = overlay_mod.overlay_summary(ws_dir)
    if not summary["has_overlay"]:
        return ""
    msg = (
        f"\nℹ️  Overlay activo: {summary['items']} item(ns), {summary['fields']} campo(s) "
        f"com correcções humanas/agente.\n"
        f"   As correcções serão reaplicadas automaticamente sobre o novo output.\n"
        f"   Para DESCARTAR o overlay: force=True (irreversível).\n"
    )
    if summary["orphans"]:
        msg += f"   ⚠️  {summary['orphans']} item(ns) no overlay não existem na base (órfãos).\n"
    return msg


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_workspaces() -> str:
    """Lista todos os workspaces existentes e o estado de cada um.

    Mostra: stage do pipeline, prova.md, questões extraídas/aprovadas/final, upload.
    """
    if not _WORKSPACE_DIR.exists():
        return "Diretório workspace não encontrado."

    workspaces = sorted(
        [d for d in _WORKSPACE_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )
    if not workspaces:
        return "Nenhum workspace encontrado."

    lines = [f"{'Workspace':<40} {'Stage':<14} {'MD':>4} {'Raw':>5} {'Apr':>5} {'Fin':>5} {'UP':>4}"]
    lines.append("-" * 78)
    for ws_dir in workspaces:
        s = _workspace_state(ws_dir)
        ws_st = WorkspaceStage(ws_dir)
        lines.append(
            f"{s['nome']:<40} "
            f"{ws_st.stage:<14} "
            f"{'✅' if s['prova_md'] else '❌':>4} "
            f"{str(s['questoes_raw'] or '-'):>5} "
            f"{str(s['questoes_aprovadas'] or '-'):>5} "
            f"{str(s['questoes_final'] or '-'):>5} "
            f"{'✅' if s['upload_done'] else '❌':>4}"
        )
    lines.append("")
    lines.append("Stage=estado pipeline | MD=prova.md | Raw=extraídas | Apr=aprovadas | Fin=final | UP=Supabase")
    return "\n".join(lines)


@mcp.tool()
def workspace_status(workspace: str) -> str:
    """Estado detalhado de um workspace + próxima acção sugerida.

    Entry-point principal de inspecção — usar sempre que em dúvida sobre o estado.

    Args:
        workspace: Nome do workspace (ex: "EX-MatA635-F1-2024_net")
    """
    ws_dir = _workspace_path(workspace)
    if not ws_dir.exists():
        return f"Workspace '{workspace}' não encontrado."

    s = _workspace_state(ws_dir)
    ws = WorkspaceStage(ws_dir)
    rev = _count_reviewed(workspace)
    reviewed_str = f"{rev[0]}/{rev[1]} revistos" if rev else "—"

    ws_dir2 = _workspace_path(workspace)
    review_label = "questoes_review.json" if (ws_dir2 / "questoes_review.json").exists() else "questoes_raw.json"
    lines = [
        f"Workspace: {s['nome']}",
        f"  estado pipeline:     {ws.stage}",
        f"  prova.md:            {'✅' if s['prova_md'] else '❌ (MinerU pendente)'}",
        f"  {review_label}:   {s['questoes_raw'] or '❌'} questões   [{reviewed_str}]",
        f"  questoes_aprovadas:  {s['questoes_aprovadas'] or '❌'} questões",
        f"  questoes_com_erro:   {s['questoes_com_erro'] or 0} erros",
        f"  questoes_final.json: {s['questoes_final'] or '❌'} questões",
    ]

    # CC workspace associado
    cc_ws_name = _find_cc_workspace(workspace)
    if cc_ws_name:
        cc_dir = _workspace_path(cc_ws_name)
        cc_ws_state = WorkspaceStage(cc_dir)
        cc_data = _workspace_state(cc_dir)
        lines.append(f"  CC workspace:        {cc_ws_name}  (estado CC: {cc_ws_state.cc_stage})")
        if cc_data["criterios_aprovados"]:
            lines.append(f"    criterios_aprovados: {cc_data['criterios_aprovados']} itens")
    else:
        lines.append(f"  CC workspace:        não detectado")

    lines.append(f"  upload Supabase:     {'✅ feito' if s['upload_done'] else '❌ pendente'}")

    # Overlay de correcções humanas/agente
    ov_summary = overlay_mod.overlay_summary(ws_dir)
    if ov_summary["has_overlay"]:
        ov_line = (
            f"  correcoes_humanas:   {ov_summary['items']} item(ns), "
            f"{ov_summary['fields']} campo(s)"
        )
        if ov_summary["orphans"]:
            ov_line += f" — ⚠️ {ov_summary['orphans']} órfão(s)"
        lines.append(ov_line)
    else:
        lines.append("  correcoes_humanas:   (sem overlay)")

    # Ficheiros adicionais
    ws_files = sorted(ws_dir.iterdir())
    outros = [f.name for f in ws_files if f.suffix in (".json", ".md", ".html") and f.name not in {
        "prova.md", "questoes_raw.json", "questoes_aprovadas.json",
        "questoes_com_erro.json", "questoes_final.json",
        "criterios_raw.json", "criterios_aprovados.json", "criterios_com_erro.json",
    }]
    if outros:
        lines.append(f"  outros ficheiros:    {', '.join(outros)}")

    # Aviso destacado se há itens excluídos do upload (validate/merge/silent_drop)
    excl = _excluded_items_summary(workspace)
    if excl["has_exclusions"]:
        lines.append("")
        lines.append(_format_exclusions_warning(excl).rstrip())

    lines.append("")
    lines.append(f"Próxima acção: {_next_action(ws_dir, workspace)}")
    return "\n".join(lines)


@mcp.tool()
def run_stage(
    workspace: str,
    stage: str,
    pdf_path: str | None = None,
    workspace_cc: str | None = None,
    pdf_cc_path: str | None = None,
    force: bool = False,
) -> str:
    """Executa um estágio do pipeline: extract | validate | cc (×2) | merge | upload | reextract-images.

    Args:
        workspace:    Nome do workspace (ex: "EX-MatA635-F1-2024_net")
        stage:        extract | validate | cc | merge | upload | reextract-images
        pdf_path:     PDF absoluto da prova (extract, se prova.md não existir;
                      reextract-images: PDF original, sem pré-processamento)
        workspace_cc: Workspace CC-VD (cc/merge; auto-detectado se omitido)
        pdf_cc_path:  PDF absoluto do CC-VD (cc, 1ª chamada, se prova.md não existir)
        force:        Ignora protecção de estado (DESTRUTIVO)

    Notas sobre reextract-images:
      Substitui as imagens em `imagens_extraidas/` por recortes do PDF original,
      eliminando o brilho/contraste artificiais do pré-processamento de OCR.
      Idempotente — backup automático em `imagens_extraidas.pre_reextract/` na
      primeira execução. Não altera `prova.md` nem JSONs (nomes são preservados).
      Pode correr a qualquer momento após `extract`, mesmo em workspaces já
      validados ou com upload feito (re-upload sobrescreve os blobs).
    """
    stage = stage.strip().lower()
    valid_stages = {"extract", "validate", "cc", "merge", "upload", "reextract-images"}
    if stage not in valid_stages:
        return (
            f"❌ Stage '{stage}' inválido.\n"
            f"Valores aceites: {', '.join(sorted(valid_stages))}"
        )

    ws_dir = _workspace_path(workspace)
    ws = WorkspaceStage(ws_dir)

    # ── extract ───────────────────────────────────────────────────────────────
    if stage == "extract":
        if not force and (err := ws.require_not_beyond("fresh")):
            return err + "\n\nPara recomeçar use force=True (DESTRUTIVO — apaga trabalho manual)."

        prova_md = ws_dir / "prova.md"

        if pdf_path:
            # Passo 1: pré-processar o PDF (pymupdf + Pillow — corre no sandbox)
            from .module_preprocess import preprocess_pdf_for_ocr  # noqa: PLC0415
            pdf_p = Path(pdf_path)
            ws_dir.mkdir(parents=True, exist_ok=True)
            try:
                preprocessed = preprocess_pdf_for_ocr(pdf_p, ws_dir)
            except Exception as exc:
                preprocessed = pdf_p
                print(f"[preprocess] ❌ {exc} — usando PDF original.")

            # Passo 2: MinerU + cotações + estruturação (timeout 900s para PDFs grandes)
            args = ["extract", str(preprocessed), "--workspace", workspace, "--no-preprocess"]
            result = _run(args, timeout=900)

            if not result["ok"]:
                # Fallback: instruir o utilizador a correr MinerU manualmente
                mineru_cmd = (
                    f".venv-mineru/bin/mineru -b pipeline"
                    f" -p '{preprocessed}'"
                    f" -o workspace/{workspace}"
                )
                return (
                    f"✅ Pré-processamento concluído → {preprocessed}\n\n"
                    f"⚠️ MinerU falhou automaticamente. Corre no Terminal:\n"
                    f"  {mineru_cmd}\n\n"
                    f"Depois: run_stage(workspace='{workspace}', stage='extract') sem pdf_path.\n\n"
                    f"Erro: {result['stderr'][:500] if result['stderr'] else result['stdout'][:500]}"
                )
        elif prova_md.exists():
            # MinerU já foi corrido manualmente e prova.md já foi copiado — só estruturar
            args = ["structure", str(prova_md)]
            result = _run(args)
        else:
            # Tentar normalizar output manual do MinerU (localiza .md via rglob)
            from .pdf_parser import normalize_mineru_workspace  # noqa: PLC0415
            ws_dir.mkdir(parents=True, exist_ok=True)
            normalized = normalize_mineru_workspace(ws_dir)
            if normalized:
                args = ["structure", str(normalized)]
                result = _run(args)
            else:
                return (
                    f"❌ Nenhum PDF nem output do MinerU encontrado em '{workspace}'.\n\n"
                    f"Opção A (recomendada): run_stage(workspace='{workspace}', stage='extract', pdf_path='<CAMINHO>')\n"
                    f"  → pré-processa o PDF e tenta correr MinerU automaticamente.\n\n"
                    f"Opção B (MinerU manual):\n"
                    f"  .venv-mineru/bin/mineru -b pipeline -p '<PDF>' -o workspace/{workspace}\n"
                    f"  Depois: run_stage(workspace='{workspace}', stage='extract') sem pdf_path\n"
                    f"  → normaliza automaticamente o output, sem copiar ficheiros à mão."
                )

        if result["ok"]:
            # Re-extrair imagens do PDF original — evita herdar brilho/contraste
            # do preprocessamento OCR. A CLI tem o mesmo passo, mas só corre
            # quando ela própria preprocessou (`if not args.no_preprocess`).
            # Como o MCP preprocessa antes e passa `--no-preprocess` à CLI,
            # esse caminho nunca é exercido — temos de o fazer aqui, com o
            # original `pdf_p` que o MCP guardou.
            reextract_msg = ""
            if pdf_path:
                try:
                    from .module_reextract_images import reextract_images  # noqa: PLC0415
                    reex = reextract_images(ws_dir, pdf_p.resolve(), verbose=False)
                    reextract_msg = f"\n[reextract] {reex.message}"
                except Exception as exc:
                    reextract_msg = (
                        f"\n[reextract] ⚠️  Re-extração de imagens falhou: {exc} "
                        "(imagens preprocessadas mantidas; correr manualmente "
                        f"`run_stage(stage='reextract-images', pdf_path=...)`)."
                    )

            ws.transition("extracted")
            return _format_result("extract", result) + reextract_msg + (
                f"\n\n📋 Próximos passos:\n"
                f"  1. Verificar cotacoes_estrutura.json (chaves: 'I-1', 'II-2.1')\n"
                f"  2. Rever questoes_review.json: reviewed:true + categorização em cada item\n"
                f"     (para verificar OCR de um item: get_question_context(workspace, id_item))\n"
                f"  3. run_stage(workspace='{workspace}', stage='validate')"
            )
        return _format_result("extract", result)

    # ── validate ──────────────────────────────────────────────────────────────
    if stage == "validate":
        raw = ws_dir / "questoes_raw.json"
        if not raw.exists():
            return (
                f"❌ questoes_raw.json não encontrado em '{workspace}'.\n"
                f"Corre run_stage(workspace='{workspace}', stage='extract') primeiro."
            )

        if not force and (err := ws.require_not_beyond("validated")):
            return err

        # Verificar se todos os itens estão revistos
        rev = _count_reviewed(workspace)
        if rev and not force:
            reviewed, total = rev
            if reviewed < total:
                return (
                    f"❌ {total - reviewed} item(ns) ainda com reviewed:false "
                    f"({reviewed}/{total} revistos).\n"
                    f"Rever todos os itens em questoes_raw.json (Read + Edit) antes de validar."
                )

        # Aviso informativo sobre overlay (validate regenera questoes_raw, overlay sobrevive)
        gate_msg = _overlay_gate_msg(ws_dir)

        # Merge review+meta → questoes_raw.json (workspaces novos com ficheiros split)
        if merge_err := _merge_review_meta(workspace):
            return merge_err

        # Passo 1 (interno): micro-lint
        lint_result = _run(["micro-lint", str(raw)])
        lint_ok = "✅" if lint_result["ok"] else "❌"
        lint_summary = lint_result["stdout"][-600:] if lint_result["stdout"] else "(sem output)"

        if not lint_result["ok"]:
            return (
                f"❌ micro-lint falhou — corrigir antes de validar:\n"
                f"{lint_summary}"
            )

        # Passo 2 (interno): validate
        val_result = _run(["validate", str(raw)])
        if val_result["ok"]:
            ws.transition("validated")

        # Aviso destacado se validate excluiu itens (foram para questoes_com_erro.json)
        excl_post_validate = _excluded_items_summary(workspace)
        validate_excl_warn = (
            "\n" + _format_exclusions_warning(excl_post_validate)
            if excl_post_validate["has_exclusions"] else ""
        )

        _next_step = (
            f"\n\n📋 Próximo passo: run_stage(workspace='{workspace}', stage='cc', "
            f"pdf_cc_path='<CAMINHO-CC-VD.pdf>')"
        ) if val_result["ok"] else ""
        return (
            gate_msg
            + f"{lint_ok} micro-lint\n{lint_summary}\n\n"
            + _format_result("validate", val_result)
            + validate_excl_warn
            + _next_step
        )

    # ── cc ────────────────────────────────────────────────────────────────────
    if stage == "cc":
        if not workspace_cc:
            workspace_cc = _find_cc_workspace(workspace)
        if not workspace_cc:
            return (
                "❌ workspace_cc não fornecido e não foi detectado automaticamente.\n"
                f"Forneça: run_stage(workspace='{workspace}', stage='cc', workspace_cc='<NOME-CC-VD>')"
            )

        ws_cc_dir = _workspace_path(workspace_cc)
        prova_cc_md = ws_cc_dir / "prova.md"

        if not prova_cc_md.exists():
            if pdf_cc_path:
                # MinerU CC-VD sem preprocess (PDFs de critérios são texto nítido)
                # timeout 900s para PDFs grandes
                cc_args = ["extract", pdf_cc_path, "--workspace", workspace_cc, "--no-preprocess"]
                cc_extract_result = _run(cc_args, timeout=900)
                if not cc_extract_result["ok"]:
                    mineru_cmd = (
                        f".venv-mineru/bin/mineru -b pipeline"
                        f" -p '{pdf_cc_path}'"
                        f" -o workspace/{workspace_cc}"
                    )
                    return (
                        f"⚠️ MinerU CC-VD falhou automaticamente. Corre no Terminal:\n"
                        f"  {mineru_cmd}\n\n"
                        f"Depois: run_stage(workspace='{workspace}', stage='cc', workspace_cc='{workspace_cc}') sem pdf_cc_path.\n\n"
                        f"Erro: {cc_extract_result['stderr'][:500] if cc_extract_result['stderr'] else cc_extract_result['stdout'][:500]}"
                    )
                # MinerU correu — normalizar output se prova.md ainda não existir
                if not prova_cc_md.exists():
                    from .pdf_parser import normalize_mineru_workspace  # noqa: PLC0415
                    normalized_cc = normalize_mineru_workspace(ws_cc_dir)
                    if not normalized_cc:
                        return f"❌ MinerU terminou mas prova.md não foi gerado em '{workspace_cc}'."
            else:
                # Tentar normalizar output manual do MinerU CC-VD (localiza .md via rglob)
                from .pdf_parser import normalize_mineru_workspace  # noqa: PLC0415
                ws_cc_dir.mkdir(parents=True, exist_ok=True)
                normalized_cc = normalize_mineru_workspace(ws_cc_dir)
                if not normalized_cc:
                    return (
                        f"❌ prova.md não encontrado em '{workspace_cc}'.\n\n"
                        f"Opção A (recomendada): run_stage(workspace='{workspace}', stage='cc', workspace_cc='{workspace_cc}', pdf_cc_path='<CAMINHO-CC-VD.pdf>')\n"
                        f"  → tenta correr MinerU automaticamente.\n\n"
                        f"Opção B (MinerU manual):\n"
                        f"  .venv-mineru/bin/mineru -b pipeline -p '<CC-VD.pdf>' -o workspace/{workspace_cc}\n"
                        f"  Depois: run_stage(workspace='{workspace}', stage='cc', workspace_cc='{workspace_cc}')\n"
                        f"  → normaliza automaticamente o output, sem copiar ficheiros à mão."
                    )

        # Gate obrigatório: prova principal deve estar validated antes de processar CC-VD
        if not force and (err := ws.require_at_least("validated")):
            return (
                f"❌ BLOQUEADO: prova principal não está validada.\n"
                f"{err}\n\n"
                f"Sequência obrigatória ANTES de processar CC-VD:\n"
                f"  1. Rever questoes_review.json (reviewed:true + categorização em cada item)\n"
                f"  2. run_stage(workspace='{workspace}', stage='validate')\n"
                f"  Só depois: run_stage(workspace='{workspace}', stage='cc', workspace_cc='{workspace_cc}')"
            )

        ws_cc = WorkspaceStage(ws_cc_dir)
        cc_st = ws_cc.cc_stage

        if cc_st == "cc_validated":
            return (
                f"✅ CC-VD já validado (estado: {cc_st}).\n"
                f"Próximo passo: run_stage(workspace='{workspace}', stage='merge', workspace_cc='{workspace_cc}')"
            )

        if cc_st == "cc_fresh":
            # 1ª chamada: extrair critérios
            cc_extract_args = ["cc-extract", str(prova_cc_md)]
            # Cruzar tipo_item da prova principal — evita classificar multi_select
            # como multiple_choice quando o OCR captura "Opção (X)" por engano.
            questoes_review_path = _workspace_path(workspace) / "questoes_review.json"
            if questoes_review_path.exists():
                cc_extract_args.extend(["--questoes-review", str(questoes_review_path)])
            result = _run(cc_extract_args)
            if result["ok"]:
                ws_cc.transition_cc("cc_extracted")
                # Verificar se há items flaggeados pelo lint OCR
                flags_path = ws_cc_dir / "criterios_ocr_flags.json"
                n_flags = 0
                if flags_path.exists():
                    try:
                        n_flags = len(json.loads(flags_path.read_text(encoding="utf-8")))
                    except Exception:
                        pass
                ocr_note = (
                    f"\n  ⚠️  {n_flags} item(ns) com suspeitas OCR em criterios_ocr_flags.json\n"
                    f"     → Ler criterios_ocr_flags.json PRIMEIRO; para cada item flaggeado\n"
                    f"       usar get_cc_context(workspace_cc='{workspace_cc}', id_item='...') para ver o OCR bruto\n"
                    f"     → Adicionar 'OCR-RESOLVED: original→correcto' ou 'OCR-FALSE-POSITIVE: justificação'\n"
                    f"       nas observacoes antes de setar reviewed:true"
                ) if n_flags else ""
                return _format_result("cc-extract", result) + (
                    f"\n\n📋 Próximos passos:\n"
                    f"  1. Ler criterios_review.json em '{workspace_cc}' (compacto, sem texto_original){ocr_note}\n"
                    f"  2. Para cada item: setar reviewed:true\n"
                    f"     • GRUPO I (MC): preencher resposta_correta (gabarito na imagem do PDF)\n"
                    f"     • Itens abertos sem etapas: extrair do bloco OCR via get_cc_context() ou PDF com Edit\n"
                    f"     • Duplicados 'II-*': apagar entradas prefixadas se existirem versões simples\n"
                    f"  3. run_stage(workspace='{workspace}', stage='cc', workspace_cc='{workspace_cc}')"
                )
            return _format_result("cc-extract", result)

        # cc_extracted: 2ª chamada (pós-revisão) → validar
        raw_cc = ws_cc_dir / "criterios_raw.json"
        if not raw_cc.exists():
            return f"❌ criterios_raw.json não encontrado em '{workspace_cc}'."

        # Merge criterios_review.json (editado pelo agente) → criterios_raw.json.
        # Sem isto, edições do agente em campos como solucao/resposta_correta/
        # criterios_parciais/reviewed são silenciosamente ignoradas.
        if merge_err := _merge_criterios_review(workspace_cc):
            return merge_err

        result = _run(["cc-validate", str(raw_cc)])
        if result["ok"]:
            ws_cc.transition_cc("cc_validated")
            return _format_result("cc-validate", result) + (
                f"\n\n📋 Próximo passo: run_stage(workspace='{workspace}', stage='merge', workspace_cc='{workspace_cc}')"
            )
        return _format_result("cc-validate", result)

    # ── merge ─────────────────────────────────────────────────────────────────
    if stage == "merge":
        if not workspace_cc:
            workspace_cc = _find_cc_workspace(workspace)
        if not workspace_cc:
            return (
                "❌ workspace_cc não fornecido e não detectado automaticamente.\n"
                f"Forneça: run_stage(workspace='{workspace}', stage='merge', workspace_cc='<NOME-CC-VD>')"
            )

        ws_cc_dir = _workspace_path(workspace_cc)
        approved = ws_dir / "questoes_aprovadas.json"
        criterios = ws_cc_dir / "criterios_aprovados.json"

        if not approved.exists():
            return f"❌ questoes_aprovadas.json não encontrado em '{workspace}'."
        if not criterios.exists():
            return f"❌ criterios_aprovados.json não encontrado em '{workspace_cc}'. Corre run_stage(stage='cc') primeiro."

        # ── HARD GATE: staleness (edição pós-validate ignorada pelo merge) ───
        # O merge lê questoes_aprovadas.json e criterios_aprovados.json. Se o
        # agente editou *_review.json depois do último validate, essas edições
        # ficam isoladas e o questoes_final.json reflecte o estado antigo —
        # confundindo o humano que vê o preview "sem alterações" mesmo após
        # um Edit explícito. Detectar por mtime e exigir re-validação.
        review_q = ws_dir / "questoes_review.json"
        if review_q.exists() and review_q.stat().st_mtime > approved.stat().st_mtime:
            return (
                "❌ questoes_review.json foi editado depois do último validate.\n"
                f"  Caminho: {review_q}\n"
                f"  Última edição: review={review_q.stat().st_mtime:.0f} > "
                f"aprovadas={approved.stat().st_mtime:.0f}\n"
                "  As edições NÃO estão em questoes_aprovadas.json — o merge ignorá-las-ia\n"
                "  e o preview mostraria o estado antigo.\n\n"
                f"  Re-correr: run_stage(workspace='{workspace}', stage='validate')\n"
                f"  Depois:   run_stage(workspace='{workspace}', stage='merge', "
                f"workspace_cc='{workspace_cc}')"
            )
        raw_cc = ws_cc_dir / "criterios_raw.json"
        if raw_cc.exists() and raw_cc.stat().st_mtime > criterios.stat().st_mtime:
            return (
                "❌ criterios_raw.json foi editado depois do último cc-validate.\n"
                f"  Caminho: {raw_cc}\n"
                f"  Última edição: raw={raw_cc.stat().st_mtime:.0f} > "
                f"aprovados={criterios.stat().st_mtime:.0f}\n"
                "  As edições NÃO estão em criterios_aprovados.json — o merge ignorá-las-ia.\n\n"
                f"  Re-correr: run_stage(workspace='{workspace}', stage='cc', "
                f"workspace_cc='{workspace_cc}')\n"
                f"  Depois:   run_stage(workspace='{workspace}', stage='merge', "
                f"workspace_cc='{workspace_cc}')"
            )
        # Mesma lógica para criterios_review.json — desde que o merge interno
        # criterios_review→criterios_raw foi adicionado, o caminho canónico de
        # edição do agente é o review. Sem este gate, edições em review feitas
        # depois do cc-validate ficariam em raw apenas após nova chamada cc, e
        # o merge corria com aprovados antigos.
        review_cc = ws_cc_dir / "criterios_review.json"
        if review_cc.exists() and review_cc.stat().st_mtime > criterios.stat().st_mtime:
            return (
                "❌ criterios_review.json foi editado depois do último cc-validate.\n"
                f"  Caminho: {review_cc}\n"
                f"  Última edição: review={review_cc.stat().st_mtime:.0f} > "
                f"aprovados={criterios.stat().st_mtime:.0f}\n"
                "  As edições NÃO estão em criterios_aprovados.json — o merge ignorá-las-ia.\n\n"
                f"  Re-correr: run_stage(workspace='{workspace}', stage='cc', "
                f"workspace_cc='{workspace_cc}')\n"
                f"  Depois:   run_stage(workspace='{workspace}', stage='merge', "
                f"workspace_cc='{workspace_cc}')"
            )

        # ── HARD GATE: validation_error em questoes_com_erro.json ────────────
        # Não bypassável com force=True. Items com erro de validação têm de ser
        # resolvidos (corrigir + re-validate, ou remover de questoes_review.json)
        # antes do merge — caso contrário acabam num final.json que não reflecte
        # o que foi de facto aprovado.
        com_erro_path = ws_dir / "questoes_com_erro.json"
        if com_erro_path.exists():
            try:
                erro_data = json.loads(com_erro_path.read_text(encoding="utf-8"))
            except Exception:
                erro_data = []
            if isinstance(erro_data, list) and erro_data:
                ids = [q.get("id_item", "?") for q in erro_data if isinstance(q, dict)]
                ids_fmt = "\n".join(f"  • {i}" for i in ids)
                return (
                    f"❌ HARD GATE: {len(ids)} item(ns) com validation_error em "
                    f"questoes_com_erro.json:\n{ids_fmt}\n\n"
                    f"Resolva ANTES do merge (esta gate NÃO é bypassável com force=True):\n"
                    f"  1. Corrigir o item em questoes_review.json e re-correr "
                    f"run_stage(stage='validate')\n"
                    f"  2. OU remover o item de questoes_review.json (se for para descartar)\n"
                    f"     e re-correr run_stage(stage='validate')\n"
                    f"  3. Se o erro vier de cotacoes↔JSON: definir "
                    f"\"bypass_validation\": true em\n"
                    f"     cotacoes_estrutura.json e re-correr validate\n\n"
                    f"Motivo: items aqui não vão para o Supabase. Permitir merge "
                    f"silencia o problema."
                )

        if not force:
            if ws.stage == "cc_merged":
                return (
                    f"ℹ️  Merge já concluído (estado: cc_merged).\n"
                    f"Próximo passo: run_review(workspace='{workspace}')"
                )
            if err := ws.require_exactly("validated"):
                return err

        # Backup preventivo antes de sobrescrever questoes_final.json
        _snapshot_before_stage(ws_dir, "merge")

        # Overlay: aviso informativo (overlay sobrevive ao re-merge)
        gate_msg = _overlay_gate_msg(ws_dir)
        if force and overlay_mod.overlay_summary(ws_dir)["has_overlay"]:
            # force=True descarta o overlay
            (ws_dir / "correcoes_humanas.json").unlink(missing_ok=True)
            gate_msg = "⚠️  Overlay descartado (force=True).\n"

        ws_cc = WorkspaceStage(ws_cc_dir)
        if err := ws_cc.require_cc_at_least("cc_validated"):
            return err

        # Gate obrigatório: categorização completa
        uncategorized = check_all_categorized(approved)
        if uncategorized:
            items_list = "\n".join(f"  • {id_}" for id_ in uncategorized)
            return (
                f"❌ BLOQUEADO: {len(uncategorized)} questão(ões) sem categorização em '{workspace}'.\n"
                f"Preencher tema, subtema, descricao_breve e tags antes do merge:\n"
                f"{items_list}\n\n"
                f"Editar directamente em questoes_aprovadas.json com Read + Edit."
            )

        # ── Gate B: verificações pré-voo (ignoradas com force=True) ──────────
        if not force:
            try:
                approved_data: list[dict] = json.loads(approved.read_text(encoding="utf-8"))
                criterios_data: list[dict] = json.loads(criterios.read_text(encoding="utf-8"))
                criterios_ids = {
                    c.get("id_item", "").lower().strip()
                    for c in criterios_data if isinstance(c, dict)
                }

                # B1: itens com status validation_error em questoes_aprovadas
                val_error_ids = [
                    q.get("id_item", "?")
                    for q in approved_data
                    if isinstance(q, dict) and q.get("status") == "validation_error"
                ]

                # B2: itens não-context_stem sem critério CC correspondente
                missing_cc: list[str] = []
                for q in approved_data:
                    if not isinstance(q, dict):
                        continue
                    if q.get("tipo_item") == "context_stem":
                        continue
                    if q.get("status") == "validation_error":
                        continue  # já capturado em B1
                    id_lower = (q.get("id_item") or str(q.get("numero_questao", ""))).lower().strip()
                    in_cc = id_lower in criterios_ids or (
                        id_lower.startswith("ii-")
                        and re.sub(r"^ii-", "", id_lower) in criterios_ids
                    )
                    if not in_cc:
                        missing_cc.append(q.get("id_item") or id_lower)

                gate_b_msgs: list[str] = []
                if val_error_ids:
                    items_fmt = "\n".join(f"  • {i}" for i in val_error_ids)
                    gate_b_msgs.append(
                        f"  {len(val_error_ids)} item(ns) com status validation_error:\n{items_fmt}\n"
                        f"  → Corrigir e re-executar run_stage(validate) para estes itens."
                    )
                if missing_cc:
                    items_fmt = "\n".join(f"  • {i}" for i in missing_cc)
                    gate_b_msgs.append(
                        f"  {len(missing_cc)} item(ns) sem critério CC correspondente:\n{items_fmt}\n"
                        f"  → Completar criterios_aprovados.json ou corrigir id_item nos critérios."
                    )
                if gate_b_msgs:
                    return (
                        gate_msg
                        + f"❌ BLOQUEADO: merge pré-voo falhou.\n\n"
                        + "\n".join(gate_b_msgs)
                        + f"\n\nPara forçar o merge excluindo os itens problemáticos: force=True\n"
                        f"  (itens excluídos ficam em questoes_merge_pendente.json)"
                    )
            except Exception:
                pass  # Se não conseguir ler, cc-merge trata internamente

        cc_merge_args = ["cc-merge", str(criterios), str(approved)]
        if force:
            cc_merge_args.append("--force")
        result = _run(cc_merge_args)
        output = gate_msg + _format_result("cc-merge", result)

        if result["ok"]:
            ws.transition("cc_merged")
            final = ws_dir / "questoes_final.json"
            if final.exists():
                # Apagar aprovação anterior e snapshot — novo merge exige nova revisão humana
                review_flag = ws_dir / ".review_approved"
                snapshot    = ws_dir / "questoes_final.approved_snapshot.json"
                if review_flag.exists():
                    review_flag.unlink()
                    ws.reset_to("cc_merged")
                snapshot.unlink(missing_ok=True)
                url = _start_preview_background(final, "preview", 8798)
                # Aviso destacado se merge excluiu itens (mesmo com force=True)
                excl_post_merge = _excluded_items_summary(workspace)
                if excl_post_merge["has_exclusions"]:
                    output += "\n\n" + _format_exclusions_warning(excl_post_merge)
                output += (
                    f"\n\n⚠️  REVISÃO HUMANA OBRIGATÓRIA antes do upload!\n"
                    f"🔍 Preview: {url}\n"
                    f"   Clique '✅ Aprovar para Upload' quando estiver satisfeito.\n"
                    f"   Depois: run_stage(workspace='{workspace}', stage='upload')"
                )
        return output

    # ── reextract-images ──────────────────────────────────────────────────────
    if stage == "reextract-images":
        if not pdf_path:
            return (
                "❌ reextract-images requer pdf_path (PDF original da prova, sem pré-processamento).\n"
                f"Ex: run_stage(workspace='{workspace}', stage='reextract-images', "
                "pdf_path='/abs/caminho/EX-Port639-F2-2023-V1.pdf')"
            )
        pdf_p = Path(pdf_path)
        if not pdf_p.exists():
            return f"❌ PDF não encontrado: {pdf_p}"

        args_cli = ["reextract-images", workspace, str(pdf_p)]
        result = _run(args_cli)
        return _format_result("reextract-images", result)

    # ── upload ────────────────────────────────────────────────────────────────
    if stage == "upload":
        base_final = ws_dir / "questoes_final.json"
        if not base_final.exists():
            base_final = ws_dir / "questoes_aprovadas.json"
        if not base_final.exists():
            return (
                f"❌ questoes_final.json não encontrado em '{workspace}'.\n"
                f"Corre run_stage(stage='merge') primeiro."
            )

        if not force and (err := ws.require_exactly("human_approved")):
            return (
                f"❌ Upload bloqueado: revisão humana obrigatória.\n"
                f"Estado actual: '{ws.stage}'\n\n"
                f"Passos:\n"
                f"  1. run_review(workspace='{workspace}') para abrir o preview\n"
                f"  2. Revise todas as questões\n"
                f"  3. Clique '✅ Aprovar para Upload' no preview\n"
                f"  4. run_stage(workspace='{workspace}', stage='upload') novamente"
            )

        # Gate: itens excluídos ao longo do pipeline (validate + merge)
        # Bloqueia upload silencioso de provas incompletas — bug observado em
        # F1/F2 2011 onde cotações incompletas levaram à rejeição massiva de MC
        # sem aviso no upload final.
        excl = _excluded_items_summary(workspace)
        if excl["has_exclusions"] and not force:
            return (
                f"❌ BLOQUEADO: prova incompleta — há itens excluídos do upload.\n\n"
                f"{_format_exclusions_warning(excl)}\n"
                f"Opções:\n"
                f"  • Resolver as exclusões (corrigir cotacoes_estrutura.json,\n"
                f"    completar criterios ou questoes) e re-correr validate/cc/merge.\n"
                f"  • Aceitar a prova parcial: run_stage(stage='upload', force=True).\n"
                f"    Use force=True APENAS após confirmar que os itens listados acima\n"
                f"    devem mesmo ficar fora do Supabase."
            )

        # Materializar overlay → ficheiro que será enviado
        mat_path, orphans = overlay_mod.materialize(ws_dir, base_final)
        if orphans:
            orphan_list = ", ".join(orphans)
            # Aviso mas não bloqueia
            orphan_warn = f"\n⚠️  Overlay tem {len(orphans)} item(ns) órfão(s) (não existem na base): {orphan_list}\n"
        else:
            orphan_warn = ""

        # HARD GATE: overlay órfão com edições humanas críticas.
        # Caso F1-2012 I-2: humano corrigiu 'alternativas' no preview, mas o item
        # ficou em questoes_com_erro.json e o overlay ficou órfão (não materializa).
        # Permitir upload aqui descartaria silenciosamente trabalho do humano.
        critical_orphans = _orphan_overlay_with_content(ws_dir, orphans)
        if critical_orphans:
            details = "\n".join(
                f"    • {iid}: campos editados = {fields}"
                for iid, fields in critical_orphans.items()
            )
            return (
                f"❌ HARD GATE: overlay tem correções humanas para "
                f"{len(critical_orphans)} item(ns) que NÃO estão em final.json:\n"
                f"{details}\n\n"
                f"Estas correções foram feitas no preview mas perder-se-iam no "
                f"upload (item está em questoes_com_erro.json ou foi removido por "
                f"re-merge).\n\n"
                f"Resolva ANTES do upload (gate NÃO bypassável com force=True):\n"
                f"  1. Re-correr validate+merge para trazer o(s) item(ns) de "
                f"volta para final.json (se a correção humana resolveu o erro)\n"
                f"  2. OU apagar a entrada órfã de correcoes_humanas.json "
                f"explicitamente (descartar a correção humana)"
            )

        # Validar contra snapshot aprovado — HARD GATE não bypassável.
        # O conteúdo enviado para Supabase TEM de ser exactamente o aprovado
        # no preview. Bypass com force=True quebraria a garantia "preview = upload"
        # que o utilizador depende para confiar no upload.
        snapshot_path = ws_dir / "questoes_final.approved_snapshot.json"
        if snapshot_path.exists():
            try:
                current_data  = json.loads(mat_path.read_text(encoding="utf-8"))
                snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
                if overlay_mod.canonical_hash(current_data) != overlay_mod.canonical_hash(snapshot_data):
                    n_cur, n_snap = len(current_data), len(snapshot_data)
                    return (
                        f"❌ HARD GATE: o conteúdo mudou após a aprovação humana.\n"
                        f"   Preview aprovado: {n_snap} item(ns)  ·  A enviar agora: {n_cur} item(ns)\n"
                        f"   O preview mostrou um estado que já não é o actual.\n\n"
                        f"Passos:\n"
                        f"  1. run_review(workspace='{workspace}') para ver o estado actual\n"
                        f"  2. Revise e clique '✅ Aprovar para Upload' novamente\n"
                        f"  3. run_stage(workspace='{workspace}', stage='upload')\n\n"
                        f"⛔ Esta gate NÃO é bypassável com force=True — se a quer ignorar,\n"
                        f"   apague {snapshot_path.name} explicitamente."
                    )
            except Exception as exc:
                return (
                    f"❌ Erro ao validar snapshot vs estado actual: {exc}\n"
                    f"   Não consigo garantir preview=upload. Re-aprovar no preview."
                )

        # Conta os items que SERÃO enviados (excluindo context_stems que vão
        # para a tabela `contextos`, não `questoes`) — para reconciliar com o
        # contador devolvido pelo Supabase abaixo.
        try:
            mat_data = json.loads(mat_path.read_text(encoding="utf-8"))
            n_questoes_a_enviar = sum(
                1 for q in mat_data
                if isinstance(q, dict) and q.get("tipo_item") != "context_stem"
            )
        except Exception:
            n_questoes_a_enviar = None

        final = mat_path  # Envia o ficheiro materializado (base + overlay)
        result = _run(["upload", str(final)], timeout=1200)

        # Aviso destacado se upload com force=True e havia exclusões — para que
        # o sucesso não dê a impressão de que a prova foi enviada inteira.
        excl_warn = (
            "\n" + _format_exclusions_warning(excl)
            if excl["has_exclusions"] else ""
        )

        # Reconciliação preview↔Supabase: parse do "[resultado] upserted=X
        # skipped=Y erros=Z" emitido pela CLI. Detecta itens silenciosamente
        # descartados durante a conversão para row do Supabase.
        upserted, skipped, n_errors = _parse_upload_resultado(result.get("stdout", ""))
        reconciliation_warn = ""
        upload_truly_ok = result["ok"]
        if upserted is not None:
            mismatch = (
                n_questoes_a_enviar is not None
                and upserted != n_questoes_a_enviar
            )
            if mismatch or (skipped or 0) > 0 or (n_errors or 0) > 0:
                upload_truly_ok = False
                reconciliation_warn = (
                    f"\n❌ RECONCILIAÇÃO FALHOU — preview ≠ Supabase:\n"
                    f"  • a enviar (questões, sem context_stems): {n_questoes_a_enviar}\n"
                    f"  • upserted no Supabase:                   {upserted}\n"
                    f"  • skipped (conversão para row falhou):    {skipped}\n"
                    f"  • erros reportados pelo upload:           {n_errors}\n\n"
                    f"⛔ Upload NÃO marcado como sucesso. Investigar antes de\n"
                    f"   considerar a prova publicada.\n"
                )

        if upload_truly_ok:
            (ws_dir / ".upload_done").touch()
            ws.transition("uploaded")
            # Backup automático após upload
            backup_result = _run(["backup"])
            backup_msg = (
                "\n✅ Backup automático concluído."
                if backup_result["ok"]
                else f"\n⚠️  Backup automático falhou: {backup_result['stderr'][:200]}"
            )
            return (
                orphan_warn + excl_warn
                + _format_result("upload", result) + backup_msg
            )

        return (
            orphan_warn + excl_warn + reconciliation_warn
            + _format_result("upload", result)
        )


@mcp.tool()
def run_review(workspace: str) -> str:
    """Abre o preview interactivo de questoes_final.json para revisão humana.

    Obrigatório entre run_stage('merge') e run_stage('upload').
    O utilizador revê as questões e clica '✅ Aprovar para Upload' para desbloquear o upload.

    Args:
        workspace: Nome do workspace com questoes_final.json
    """
    final = _workspace_path(workspace) / "questoes_final.json"
    if not final.exists():
        approved = _workspace_path(workspace) / "questoes_aprovadas.json"
        if approved.exists():
            final = approved
        else:
            return (
                f"❌ questoes_final.json não encontrado em '{workspace}'.\n"
                f"Corre run_stage(stage='merge') primeiro."
            )

    url = _start_preview_background(final, "preview", 8798)
    review_flag = _workspace_path(workspace) / ".review_approved"
    status = "✅ Já aprovado" if review_flag.exists() else "⏳ Aguarda aprovação humana"

    # Aviso pré-aprovação: o humano precisa de saber se a prova está incompleta
    # (validation_errors / merge_pendente / silent_drop) ANTES de clicar
    # "✅ Aprovar para Upload" — caso contrário aprova achando que está completa.
    excl = _excluded_items_summary(workspace)
    excl_warn = (
        "\n" + _format_exclusions_warning(excl) +
        "  → Resolva as exclusões antes de aprovar OU confirme que está OK enviar a prova parcial.\n"
    ) if excl["has_exclusions"] else ""

    return (
        f"🔍 Preview: {url}\n"
        f"   Estado: {status}\n"
        + excl_warn +
        f"\nInstruções:\n"
        f"  1. Revise todas as questões e critérios\n"
        f"  2. Use os botões ✏️ para editar inline qualquer campo\n"
        f"  3. Clique '✅ Aprovar para Upload' na barra inferior quando satisfeito\n"
        f"  4. Depois: run_stage(workspace='{workspace}', stage='upload')\n\n"
        f"Para correcções pontuais: run_fix_question(workspace, id_item, field, value)"
    )


@mcp.tool()
def run_fix_question(
    workspace: str,
    id_item: str | None = None,
    field: str | None = None,
    value: str | None = None,
    fixes_json: str | None = None,
) -> str:
    """Corrige campo(s) de uma questão via overlay — não destrutivo, não re-extrai.

    Modo simples (um campo):
        run_fix_question(workspace, id_item="II-3.2", field="enunciado", value="…")

    Modo lote (vários campos/itens):
        run_fix_question(workspace, fixes_json='[{"id_item":"II-3.2","field":"enunciado","value":"…"},…]')

    Campos editáveis: enunciado, solucao, resposta_correta, descricao_breve,
                      tema, subtema, tags (JSON array), observacoes (JSON array)

    O overlay (correcoes_humanas.json) é aplicado automaticamente no preview e no upload.
    A aprovação anterior é resetada — o humano deve rever e aprovar novamente.

    Args:
        workspace:  Nome do workspace
        id_item:    ID do item (ex: "II-3.2") — modo simples
        field:      Campo a alterar — modo simples
        value:      Novo valor — modo simples
        fixes_json: JSON array de {id_item, field, value} — modo lote
    """
    import json as _json

    ws_dir = _workspace_path(workspace)
    ws = WorkspaceStage(ws_dir)
    if err := ws.require_at_least("validated"):
        return err

    # Verificar que existe a base de dados das questões
    base_path = ws_dir / "questoes_final.json"
    if not base_path.exists():
        base_path = ws_dir / "questoes_aprovadas.json"
    if not base_path.exists():
        return f"❌ questoes_final.json não encontrado em '{workspace}'."

    ALLOWED = {
        "enunciado", "solucao", "resposta_correta", "descricao_breve",
        "tema", "subtema", "tags", "observacoes",
    }

    # Construir lista de correções
    if fixes_json:
        try:
            fixes = _json.loads(fixes_json)
            if not isinstance(fixes, list):
                return "❌ fixes_json deve ser um JSON array."
        except _json.JSONDecodeError as exc:
            return f"❌ fixes_json inválido: {exc}"
    elif id_item and field and value is not None:
        fixes = [{"id_item": id_item, "field": field, "value": value}]
    else:
        return "❌ Forneça (id_item + field + value) ou fixes_json."

    # Ler base para validar existência dos itens
    try:
        data = _json.loads(base_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"❌ Erro ao ler {base_path.name}: {exc}"

    base_ids = {str(q.get("id_item", "")) for q in data}

    results: list[str] = []
    errors:  list[str] = []

    for fix in fixes:
        fid   = str(fix.get("id_item", ""))
        fld   = str(fix.get("field", ""))
        fval  = fix.get("value", "")

        if fid not in base_ids:
            errors.append(f"  • {fid}: item não encontrado")
            continue
        if fld not in ALLOWED:
            errors.append(
                f"  • {fid}.{fld}: campo não permitido "
                f"(permitidos: {', '.join(sorted(ALLOWED))})"
            )
            continue

        # Campos que esperam array (tags, observacoes): parsear se vier como string
        if fld in ("tags", "observacoes") and isinstance(fval, str):
            try:
                fval = _json.loads(fval)
            except _json.JSONDecodeError:
                errors.append(
                    f"  • {fid}.{fld}: valor inválido — deve ser JSON array"
                    f' (ex: ["tag1","tag2"])'
                )
                continue

        overlay_mod.set_override(ws_dir, fid, fld, fval, source="agent")
        results.append(f"  • {fid}.{fld} ✅")

    if not results:
        return "❌ Nenhuma correcção aplicada.\n" + "\n".join(errors)

    # Resetar aprovação — nova correcção exige nova revisão humana
    review_flag   = ws_dir / ".review_approved"
    snapshot_path = ws_dir / "questoes_final.approved_snapshot.json"
    if review_flag.exists():
        review_flag.unlink()
        snapshot_path.unlink(missing_ok=True)
        has_final = (ws_dir / "questoes_final.json").exists()
        ws.reset_to("cc_merged" if has_final else "validated")
        reapproval_msg = "\n⚠️  Aprovação resetada — o agente corrigiu após a aprovação."
    else:
        reapproval_msg = ""

    error_section = ("\n\nErros:\n" + "\n".join(errors)) if errors else ""

    return (
        f"✅ {len(results)} correcção(ões) gravadas no overlay (correcoes_humanas.json):"
        f"\n" + "\n".join(results)
        + error_section
        + reapproval_msg
        + f"\n\nO preview e o upload aplicam o overlay automaticamente."
        + f"\nUse run_review(workspace='{workspace}') para verificar o estado final e aprovar."
    )


@mcp.tool()
def run_fix_cc(
    workspace: str,
    id_item: str | None = None,
    field: str | None = None,
    value: str | None = None,
    fixes_json: str | None = None,
) -> str:
    """Corrige campo(s) de critérios de classificação via overlay — não destrutivo.

    Modo simples:
        run_fix_cc(workspace, id_item="II-3.2", field="solucao", value="…")

    Modo lote:
        run_fix_cc(workspace, fixes_json='[{"id_item":"II-3.2","field":"solucao","value":"…"},…]')

    Campos editáveis: solucao, criterios_parciais (JSON array), resolucoes_alternativas (JSON array)

    Args:
        workspace:  Nome do workspace (principal, onde está questoes_final.json)
        id_item:    ID do item — modo simples
        field:      Campo a alterar — modo simples
        value:      Novo valor — modo simples
        fixes_json: JSON array de {id_item, field, value} — modo lote
    """
    import json as _json

    ws_dir = _workspace_path(workspace)
    ws = WorkspaceStage(ws_dir)
    if err := ws.require_at_least("cc_merged"):
        return (
            f"❌ run_fix_cc requer estado ≥ cc_merged (merge já concluído).\n"
            f"{err}\n"
            f"Para corrigir critérios antes do merge: edite criterios_aprovados.json directamente."
        )

    base_path = ws_dir / "questoes_final.json"
    if not base_path.exists():
        return f"❌ questoes_final.json não encontrado em '{workspace}'."

    ALLOWED_CC = {"solucao", "criterios_parciais", "resolucoes_alternativas"}

    if fixes_json:
        try:
            fixes = _json.loads(fixes_json)
            if not isinstance(fixes, list):
                return "❌ fixes_json deve ser um JSON array."
        except _json.JSONDecodeError as exc:
            return f"❌ fixes_json inválido: {exc}"
    elif id_item and field and value is not None:
        fixes = [{"id_item": id_item, "field": field, "value": value}]
    else:
        return "❌ Forneça (id_item + field + value) ou fixes_json."

    try:
        data = _json.loads(base_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"❌ Erro ao ler questoes_final.json: {exc}"

    base_ids = {str(q.get("id_item", "")) for q in data}
    results: list[str] = []
    errors:  list[str] = []

    for fix in fixes:
        fid  = str(fix.get("id_item", ""))
        fld  = str(fix.get("field", ""))
        fval = fix.get("value", "")

        if fid not in base_ids:
            errors.append(f"  • {fid}: item não encontrado")
            continue
        if fld not in ALLOWED_CC:
            errors.append(
                f"  • {fid}.{fld}: campo não permitido "
                f"(permitidos: {', '.join(sorted(ALLOWED_CC))})"
            )
            continue

        # Campos array: parsear se vier como string (suporta 1 ou 2 níveis de encoding)
        if fld in ("criterios_parciais", "resolucoes_alternativas"):
            for _ in range(2):  # tolera double-encoding
                if not isinstance(fval, str):
                    break
                try:
                    fval = _json.loads(fval)
                except _json.JSONDecodeError:
                    break
            if not isinstance(fval, list):
                errors.append(
                    f"  • {fid}.{fld}: valor deve ser um array JSON (lista de dicts),"
                    f" recebido {type(fval).__name__!r}"
                )
                continue

        overlay_mod.set_override(ws_dir, fid, fld, fval, source="agent")
        results.append(f"  • {fid}.{fld} ✅")

    if not results:
        return "❌ Nenhuma correcção aplicada.\n" + "\n".join(errors)

    # Resetar aprovação
    review_flag   = ws_dir / ".review_approved"
    snapshot_path = ws_dir / "questoes_final.approved_snapshot.json"
    if review_flag.exists():
        review_flag.unlink()
        snapshot_path.unlink(missing_ok=True)
        ws.reset_to("cc_merged")
        reapproval_msg = "\n⚠️  Aprovação resetada — critérios corrigidos após aprovação."
    else:
        reapproval_msg = ""

    error_section = ("\n\nErros:\n" + "\n".join(errors)) if errors else ""

    return (
        f"✅ {len(results)} correcção(ões) CC gravadas no overlay:"
        f"\n" + "\n".join(results)
        + error_section
        + reapproval_msg
        + f"\n\nUse run_review(workspace='{workspace}') para verificar e aprovar."
    )


@mcp.tool()
def get_question_context(workspace: str, id_item: str, pad: int = 3) -> str:
    """Devolve o bloco bruto de prova.md para um item sem ler o ficheiro inteiro.

    Útil para verificar OCR ou texto truncado de um item específico.

    Args:
        workspace: Nome do workspace
        id_item:   ID do item (ex: "II-3.2", "I-5")
        pad:       Linhas extra antes/depois do bloco (default: 3)
    """
    ws_dir = _workspace_path(workspace)

    # Procurar source_span: prefere questoes_meta.json, cai em questoes_raw.json
    source_span: dict | None = None
    for fname in ("questoes_meta.json", "questoes_raw.json"):
        path = ws_dir / fname
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
            for item in items:
                if str(item.get("id_item", "")) == id_item:
                    source_span = item.get("source_span")
                    break
            if source_span:
                break
        except Exception:
            continue

    if not source_span:
        return (
            f"❌ Item '{id_item}' não encontrado ou sem source_span em '{workspace}'.\n"
            f"Verifique o id_item com workspace_status('{workspace}')."
        )

    prova_md = ws_dir / "prova.md"
    if not prova_md.exists():
        return f"❌ prova.md não encontrado em '{workspace}'."

    lines = prova_md.read_text(encoding="utf-8").splitlines()
    line_start = max(0, source_span.get("line_start", 1) - 1 - pad)
    line_end   = min(len(lines), source_span.get("line_end", 1) + pad)

    excerpt = lines[line_start:line_end]
    numbered = [f"{line_start + i + 1:4d} | {ln}" for i, ln in enumerate(excerpt)]
    return (
        f"prova.md — linhas {line_start + 1}–{line_end} (item {id_item}):\n"
        + "\n".join(numbered)
    )


@mcp.tool()
def get_context_stem_pdf_pages(workspace: str, id_item: str) -> str:
    """Para um context_stem, devolve o caminho do PDF + excerto OCR + posição relativa.

    Fluxo obrigatório de revisão de números de linha em context_stem:
      1. Chamar esta tool com o id_item do context_stem (ex: "I-ctx1").
      2. Abrir o PDF nas páginas indicadas com Read(file_path=<pdf>, pages="<N>-<M>").
      3. Contar visualmente os marcadores de linha na margem do excerto.
      4. Decidir tem_numeracao_linhas (true/false) e, se true, editar o enunciado
         em questoes_review.json para ficar no formato canónico '\\n{N} …' — cada
         marcador em início de linha próprio, seguido de um espaço e do conteúdo
         daquela linha. Nunca deixar um número fundido ao texto ou inline no meio
         de uma frase.
      5. Marcar linhas_verificadas=true.

    Args:
        workspace: Nome do workspace (ex: "EX-Port639-F1-2024")
        id_item:   ID do context_stem (ex: "I-ctx1", "II-ctx1")
    """
    ws_dir = _workspace_path(workspace)
    prova_md = ws_dir / "prova.md"
    pdf_path = ws_dir / "preprocessed_input.pdf"
    if not prova_md.exists():
        return f"❌ prova.md não encontrado em '{workspace}'."
    if not pdf_path.exists():
        return f"❌ preprocessed_input.pdf não encontrado em '{workspace}'."

    source_span: dict | None = None
    tipo_item: str | None = None
    for fname in ("questoes_meta.json", "questoes_raw.json"):
        path = ws_dir / fname
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
            for item in items:
                if str(item.get("id_item", "")) == id_item:
                    source_span = item.get("source_span")
                    tipo_item = item.get("tipo_item")
                    break
            if source_span is not None:
                break
        except Exception:
            continue

    if tipo_item is not None and tipo_item != "context_stem":
        return (
            f"❌ Item '{id_item}' não é context_stem (tipo={tipo_item}). "
            "Esta tool só se aplica a context_stem."
        )
    if not source_span:
        return f"❌ Item '{id_item}' não encontrado ou sem source_span em '{workspace}'."

    lines = prova_md.read_text(encoding="utf-8").splitlines()
    total_lines = len(lines) or 1
    line_start = max(1, int(source_span.get("line_start", 1)))
    line_end = max(line_start, int(source_span.get("line_end", line_start)))
    frac_start = (line_start - 1) / total_lines
    frac_end = line_end / total_lines

    # Estimativa conservadora de páginas a abrir: assume distribuição uniforme
    # do prova.md pelo PDF (heurística; o agente deve ajustar se bater vazio).
    try:
        from pypdf import PdfReader  # type: ignore
        total_pages = len(PdfReader(str(pdf_path)).pages)
    except Exception:
        total_pages = 0

    if total_pages:
        pg_from = max(1, int(frac_start * total_pages) + 1 - 1)
        pg_to = min(total_pages, int(frac_end * total_pages) + 1 + 1)
        pages_hint = f"{pg_from}-{pg_to}" if pg_from != pg_to else f"{pg_from}"
    else:
        pages_hint = "?"

    lo = max(0, line_start - 1 - 3)
    hi = min(len(lines), line_end + 3)
    excerpt = [f"{lo + i + 1:4d} | {ln}" for i, ln in enumerate(lines[lo:hi])]

    return (
        f"context_stem '{id_item}' em '{workspace}':\n"
        f"  PDF:    {pdf_path}\n"
        f"  Páginas prováveis (heurística): {pages_hint}  (de {total_pages or '?'} total)\n"
        f"  prova.md linhas: {line_start}–{line_end} (de {total_lines})\n\n"
        f"Fluxo obrigatório:\n"
        f"  1. Read(file_path='{pdf_path}', pages='{pages_hint}')\n"
        f"  2. Contar marcadores de linha na margem do excerto.\n"
        f"  3. Editar questoes_review.json:\n"
        f"       - enunciado no formato '\\n{{N}} …' para cada marcador\n"
        f"       - tem_numeracao_linhas = true | false\n"
        f"       - linhas_verificadas = true\n\n"
        f"Excerto actual de prova.md:\n" + "\n".join(excerpt)
    )


@mcp.tool()
def get_cc_context(workspace_cc: str, id_item: str) -> str:
    """Devolve o texto_original de um critério CC sem ler criterios_raw.json inteiro.

    Útil para verificar o OCR bruto de um item flaggeado (OCR-SUSPECT) sem carregar
    o ficheiro completo. Análogo a get_question_context() mas para critérios CC-VD.

    Args:
        workspace_cc: Nome do workspace CC-VD (ex: "EX-MatA635-F1-2024-CC-VD")
        id_item:      ID do critério (ex: "3.1", "5", "II-2")
    """
    ws_dir = _workspace_path(workspace_cc)
    raw_path = ws_dir / "criterios_raw.json"

    if not raw_path.exists():
        return (
            f"❌ criterios_raw.json não encontrado em '{workspace_cc}'.\n"
            f"Corre run_stage(stage='cc') primeiro."
        )

    try:
        criterios: list[dict] = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"❌ Erro ao ler criterios_raw.json: {exc}"

    for c in criterios:
        if str(c.get("id_item", "")) == id_item:
            texto = c.get("texto_original", "")
            obs_suspects = [o for o in c.get("observacoes", []) if o.startswith("OCR-SUSPECT:")]
            header = f"criterios_raw.json — item {id_item} (texto_original):"
            if obs_suspects:
                header += f"\n⚠️  Suspeitas OCR: {len(obs_suspects)}"
                for s in obs_suspects:
                    header += f"\n   {s}"
            if not texto:
                return f"{header}\n\n(texto_original vazio — item ausente do markdown CC)"
            return f"{header}\n\n{texto}"

    return (
        f"❌ Item '{id_item}' não encontrado em criterios_raw.json de '{workspace_cc}'.\n"
        f"IDs disponíveis: {', '.join(str(c.get('id_item','?')) for c in criterios)}"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
