"""
Módulo CC-Merge — Junta critérios de classificação com as questões aprovadas.

Faz join por id_item entre criterios_aprovados.json e questoes_aprovadas.json,
preenchendo os campos resposta_correta, solucao, criterios_parciais e
resolucoes_alternativas em cada questão.

Saída: questoes_final.json no directório de questoes_aprovadas.json.

Itens sem correspondência nos critérios, com tipo divergente ou com suspeita de
contaminação são excluídos de questoes_final.json e gravados em
questoes_merge_pendente.json. Se houver pendentes e force=False, o processo
termina com código 1 (o MCP não transiciona para cc_merged).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .schemas import (
    CriterioRaw,
    Question,
    dump_questions,
    load_criterios,
    load_questions,
)
_ITEM_HEADING_RE = re.compile(r"(?m)^#{0,4}\s*(\d{1,2}(?:\.\d+)?)\.(?:[ \t]*\.)?[ \t]+\d+\s*pontos\b")
_FOREIGN_ITEM_REF_RE = re.compile(r"\b(\d{1,2}(?:\.\d+)?)\.\s+\d+\s*pontos\b", re.IGNORECASE)
_VERSAO_LINE_RE = re.compile(r"^\s*Versão\s+(\d+)\s*[:\-−–]\s*(.*)$", re.IGNORECASE)
# Tipos com resposta objectiva onde múltiplas versões da prova partilham o mesmo
# enunciado mas têm chave diferente. Para o catálogo ficamos só com a Versão 1.
_TIPOS_VERSAO_FILTRO = {"multi_select", "complete_table", "multiple_choice"}


def _keep_only_v1(text: str, tipo: str | None) -> str:
    """Se `text` contém «Versão 1 ...\\n Versão 2 ...» e o tipo é objectivo,
    devolve apenas o conteúdo da Versão 1 (sem o rótulo). Caso contrário,
    devolve `text` intacto."""
    if tipo not in _TIPOS_VERSAO_FILTRO:
        return text
    if not text or "Versão 1" not in text or "Versão 2" not in text:
        return text
    for line in text.splitlines():
        m = _VERSAO_LINE_RE.match(line)
        if m and m.group(1) == "1":
            return m.group(2).strip()
    return text


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


def merge_cc(criterios_path: Path, questoes_path: Path, force: bool = False) -> Path:
    """
    Junta criterios_aprovados.json + questoes_aprovadas.json por id_item.

    Questões sem critério correspondente, com tipo divergente ou com suspeita
    de contaminação são excluídas de questoes_final.json e gravadas em
    questoes_merge_pendente.json.

    Se force=False (padrão) e existirem itens pendentes, termina com sys.exit(1)
    para que o MCP não transicione para cc_merged.

    Devolve o caminho do questoes_final.json gerado.
    """
    criterios_path = criterios_path.resolve()
    questoes_path  = questoes_path.resolve()
    output_path    = questoes_path.parent / "questoes_final.json"
    pendente_path  = questoes_path.parent / "questoes_merge_pendente.json"

    criterios: list[CriterioRaw] = load_criterios(criterios_path)
    questoes:  list[Question]    = load_questions(questoes_path)

    # Pré-condição: id_item nunca pode estar vazio nas questões aprovadas, sob
    # pena de o merge fazer match em chave "" e juntar critérios errados.
    questoes_sem_id = [
        q for q in questoes
        if not (q.id_item or "").strip() and q.tipo_item != "context_stem"
    ]
    if questoes_sem_id:
        print(
            f"[cc_merge] ❌ {len(questoes_sem_id)} questão(ões) com id_item vazio — "
            "merge abortado para evitar associação cruzada."
        )
        for q in questoes_sem_id:
            print(f"  · numero_questao={q.numero_questao} tipo={q.tipo_item}")
        sys.exit(1)

    # Índice de critérios por id_item (normalizado para minúsculas)
    criterio_map: dict[str, CriterioRaw] = {
        c.id_item.lower().strip(): c for c in criterios
    }

    final_items:   list[Question] = []  # vai para questoes_final.json
    pendente_items: list[Question] = []  # vai para questoes_merge_pendente.json

    n_merged       = 0
    n_context_stem = 0
    n_missing      = 0
    n_blocked      = 0

    for q in questoes:
        # context_stem: inclui directamente sem merge de CC (não precisam de critério)
        if q.tipo_item == "context_stem":
            q.observacoes = list(q.observacoes) + [
                "cc_merge: critério ignorado porque o item é apenas contexto/stem."
            ]
            final_items.append(q)
            n_context_stem += 1
            print(f"[cc_merge] ⏭️  {q.id_item} — context_stem, incluído sem merge")
            continue

        key = (q.id_item or str(q.numero_questao)).lower().strip()
        criterio = criterio_map.get(key)
        # Fallback: tentar sem o prefixo de grupo, mas só para itens do Grupo II
        # (Grupo I tem os mesmos números que Grupo II e causaria matches errados)
        if criterio is None and key.startswith("ii-"):
            plain_key = re.sub(r"^ii-", "", key)
            criterio = criterio_map.get(plain_key)

        if criterio is None:
            q.observacoes = list(q.observacoes) + [
                f"cc_merge: sem critério correspondente para id_item '{q.id_item}'"
            ]
            pendente_items.append(q)
            n_missing += 1
            print(f"[cc_merge] ❌ {q.id_item} — sem critério (excluído de questoes_final.json)")
            continue

        # Verificar coerência de tipo entre critério e questão
        if criterio.tipo != q.tipo_item:
            aviso = (
                f"cc_merge: tipo do critério ('{criterio.tipo}') diverge do tipo "
                f"da questão ('{q.tipo_item}') — merge bloqueado"
            )
            q.observacoes = list(q.observacoes) + [f"AVISO: {aviso}"]
            pendente_items.append(q)
            n_blocked += 1
            print(f"[cc_merge] ❌ {q.id_item} — tipo mismatch: criterio={criterio.tipo} questao={q.tipo_item} (excluído)")
            continue

        contamination_issues = _looks_contaminated_for_item(q, criterio)
        if contamination_issues:
            q.observacoes = list(q.observacoes) + [
                f"AVISO: cc_merge bloqueado por possível contaminação: {'; '.join(contamination_issues)}"
            ]
            pendente_items.append(q)
            n_blocked += 1
            print(f"[cc_merge] ❌ {q.id_item} — possível contaminação (excluído)")
            continue

        # Merge bem-sucedido
        # Só copiar resposta_correta se o critério for MC; caso contrário preservar
        if criterio.tipo == "multiple_choice":
            q.resposta_correta = criterio.resposta_correta or q.resposta_correta
        elif criterio.tipo in {"multi_select", "complete_table"}:
            # Lista de respostas (ex: ["I","III","IV"]) — preservar se o critério vier vazio
            q.respostas_corretas = criterio.respostas_corretas or q.respostas_corretas
            # Limpar resposta_correta para evitar lixo MC herdado de extrações anteriores
            q.resposta_correta = None
        q.solucao = _keep_only_v1(criterio.solucao, q.tipo_item) if criterio.solucao else criterio.solucao
        if criterio.criterios_parciais:
            q.criterios_parciais = [
                {**cp, "descricao": _keep_only_v1(str(cp.get("descricao", "")), q.tipo_item)}
                for cp in criterio.criterios_parciais
            ]
        else:
            q.criterios_parciais = criterio.criterios_parciais
        q.resolucoes_alternativas = criterio.resolucoes_alternativas
        final_items.append(q)
        n_merged += 1
        print(f"[cc_merge] ✅ {q.id_item} ← {criterio.tipo}")

    # Gravar questoes_final.json apenas com itens fundidos + context_stems
    dump_questions(output_path, final_items)

    # Gravar questoes_merge_pendente.json (ou limpar se não há pendentes)
    if pendente_items:
        dump_questions(pendente_path, pendente_items)
    elif pendente_path.exists():
        pendente_path.unlink()

    print(
        f"\n[cc_merge] {n_merged} questões fundidas · "
        f"{n_context_stem} context_stems · "
        f"{n_missing} sem critério · "
        f"{n_blocked} bloqueados"
    )
    print(f"[cc_merge] → {output_path}")
    if pendente_items:
        print(f"[cc_merge] ⚠️  {len(pendente_items)} item(ns) excluídos → {pendente_path}")

    # Checagem de categorização (apenas nos itens finais não-context_stem)
    sem_cat = [
        q.id_item for q in final_items
        if q.tipo_item != "context_stem"
        and (not q.tema or q.tema.strip().lower() in {"", "por categorizar"})
    ]
    if sem_cat:
        print(f"\n[cc_merge] ⚠️  {len(sem_cat)} questão(ões) SEM CATEGORIZAÇÃO: {sem_cat}")
        print("[cc_merge] ℹ️  Execute a categorização antes do upload.")
    else:
        print("[cc_merge] ✅ Todas as questões estão categorizadas.")

    # Bloquear se há pendentes e não é força
    if pendente_items and not force:
        print(
            f"\n[cc_merge] ❌ BLOQUEADO: {len(pendente_items)} item(ns) sem critério ou com merge "
            f"bloqueado foram excluídos de questoes_final.json.\n"
            f"   Corrija os critérios em criterios_aprovados.json e re-execute o merge.\n"
            f"   Use --force para incluir apenas os itens fundidos e ignorar os pendentes."
        )
        sys.exit(1)

    return output_path
