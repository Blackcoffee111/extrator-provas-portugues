"""
Módulo CC-Merge — Junta critérios de classificação com as questões aprovadas.

Faz join por id_item entre criterios_aprovados.json e questoes_aprovadas.json,
preenchendo os campos resposta_correta, solucao, criterios_parciais e
resolucoes_alternativas em cada questão.

Saída: questoes_final.json no directório de questoes_aprovadas.json.

Itens sem correspondência nos critérios ficam marcados com observação.
"""
from __future__ import annotations

import re
from pathlib import Path

from .schemas import (
    CriterioRaw,
    Question,
    dump_questions,
    load_criterios,
    load_questions,
)
from .module_preview import generate_preview


_ITEM_HEADING_RE = re.compile(r"(?m)^#{0,4}\s*(\d{1,2}(?:\.\d+)?)\.(?:[ \t]*\.)?[ \t]+\d+\s*pontos\b")
_FOREIGN_ITEM_REF_RE = re.compile(r"\b(\d{1,2}(?:\.\d+)?)\.\s+\d+\s*pontos\b", re.IGNORECASE)


def _strip_group_prefix(item_id: str) -> str:
    return re.sub(r"^[ivx]+-", "", item_id.strip(), flags=re.IGNORECASE)


def _looks_contaminated_for_item(question: Question, criterio: CriterioRaw) -> list[str]:
    issues: list[str] = []
    expected_id = _strip_group_prefix(question.id_item or "")
    texts = [criterio.solucao or ""]
    texts.extend(str(cp.get("descricao", "")) for cp in (criterio.criterios_parciais or []))

    for text in texts:
        if not text:
            continue
        for match in _ITEM_HEADING_RE.finditer(text):
            found_id = match.group(1)
            if found_id != expected_id:
                issues.append(f"critério contém cabeçalho de outro item ({found_id})")
                break
        if issues:
            break

    if not issues:
        joined = "\n".join(texts)
        foreign_ids = {
            found for found in _FOREIGN_ITEM_REF_RE.findall(joined)
            if found != expected_id
        }
        if foreign_ids:
            issues.append(
                "critério refere estrutura típica de outro item: "
                + ", ".join(sorted(foreign_ids))
            )
    return issues


def merge_cc(criterios_path: Path, questoes_path: Path) -> Path:
    """
    Junta criterios_aprovados.json + questoes_aprovadas.json por id_item.

    Devolve o caminho do questoes_final.json gerado.
    """
    criterios_path = criterios_path.resolve()
    questoes_path  = questoes_path.resolve()
    output_path    = questoes_path.parent / "questoes_final.json"

    criterios: list[CriterioRaw] = load_criterios(criterios_path)
    questoes:  list[Question]    = load_questions(questoes_path)

    # Índice de critérios por id_item (normalizado para minúsculas)
    criterio_map: dict[str, CriterioRaw] = {
        c.id_item.lower().strip(): c for c in criterios
    }

    n_merged  = 0
    n_missing = 0

    for q in questoes:
        key = (q.id_item or str(q.numero_questao)).lower().strip()
        criterio = criterio_map.get(key)
        # Fallback: tentar sem o prefixo de grupo, mas só para itens do Grupo II
        # (Grupo I tem os mesmos números que Grupo II e causaria matches errados)
        if criterio is None and key.startswith("ii-"):
            plain_key = re.sub(r"^ii-", "", key)
            criterio = criterio_map.get(plain_key)

        if criterio is None:
            obs = list(q.observacoes) + [
                f"cc_merge: sem critério correspondente para id_item '{q.id_item}'"
            ]
            q.observacoes = obs
            n_missing += 1
            print(f"[cc_merge] ⚠️  {q.id_item} — sem critério")
            continue

        # Não fundir critérios em stems/contextos estruturais.
        if q.tipo_item == "context_stem":
            q.observacoes = list(q.observacoes) + [
                "cc_merge: critério ignorado porque o item é apenas contexto/stem."
            ]
            print(f"[cc_merge] ⏭️  {q.id_item} — context_stem, merge ignorado")
            continue

        # Verificar coerência de tipo entre critério e questão
        tipo_mismatch = criterio.tipo != q.tipo_item
        if tipo_mismatch:
            aviso = (
                f"cc_merge: tipo do critério ('{criterio.tipo}') diverge do tipo "
                f"da questão ('{q.tipo_item}') — merge bloqueado"
            )
            q.observacoes = list(q.observacoes) + [f"AVISO: {aviso}"]
            print(f"[cc_merge] ⚠️  {q.id_item} — tipo mismatch: criterio={criterio.tipo} questao={q.tipo_item}")
            continue

        contamination_issues = _looks_contaminated_for_item(q, criterio)
        if contamination_issues:
            q.observacoes = list(q.observacoes) + [
                f"AVISO: cc_merge bloqueado por possível contaminação: {'; '.join(contamination_issues)}"
            ]
            print(f"[cc_merge] ⚠️  {q.id_item} — possível contaminação, merge bloqueado")
            continue

        # Só copiar resposta_correta se o critério for MC; caso contrário preservar
        if criterio.tipo == "multiple_choice":
            q.resposta_correta = criterio.resposta_correta or q.resposta_correta
        q.solucao               = criterio.solucao
        q.criterios_parciais    = criterio.criterios_parciais
        q.resolucoes_alternativas = criterio.resolucoes_alternativas
        n_merged += 1
        icon = "⚠️ " if tipo_mismatch else "✅"
        print(f"[cc_merge] {icon} {q.id_item} ← {criterio.tipo}")

    dump_questions(output_path, questoes)
    preview_path = generate_preview(output_path, output_path.parent / "prova_preview.html")

    print(f"\n[cc_merge] {n_merged} questões com critérios · {n_missing} sem correspondência")
    print(f"[cc_merge] → {output_path}")
    print(f"[cc_merge] 🔍 Preview HTML gerado → {preview_path}")

    # Checagem de categorização
    sem_cat = [
        q.id_item for q in questoes
        if not q.tema or q.tema.strip().lower() in {"", "por categorizar"}
    ]
    if sem_cat:
        print(f"\n[cc_merge] ⚠️  {len(sem_cat)} questão(ões) SEM CATEGORIZAÇÃO: {sem_cat}")
        print("[cc_merge] ℹ️  Execute a categorização antes do upload.")
    else:
        print("[cc_merge] ✅ Todas as questões estão categorizadas.")

    return output_path
