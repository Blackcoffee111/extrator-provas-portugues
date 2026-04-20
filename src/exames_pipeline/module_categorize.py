from __future__ import annotations

"""Módulo 5 — Categorização de questões.

A categorização é feita pelo agente Claude Code directamente,
lendo o questoes_aprovadas.json e preenchendo tema, subtema,
descricao_breve e tags com as ferramentas Read + Edit.

Este módulo fornece apenas a função que verifica quais questões
ainda precisam de categorização, sem chamar nenhuma API externa.
"""

from pathlib import Path

from .schemas import Question, dump_questions, load_questions


def _needs_categorization(q: Question) -> bool:
    return not (
        (q.tema or "").strip()
        and (q.subtema or "").strip()
        and (q.descricao_breve or "").strip()
        and q.tags
        and q.tema.strip().lower() != "por categorizar"
        and q.subtema.strip().lower() != "por categorizar"
    )


def check_all_categorized(approved_path: Path) -> list[str]:
    """Retorna lista de id_item não categorizados em questoes_aprovadas.json.

    Lista vazia = todas categorizadas (pode prosseguir).
    Usada como gate obrigatório antes do run_cc_merge.
    """
    questions = load_questions(approved_path)
    return [q.id_item for q in questions if _needs_categorization(q)]


def categorize_questions(settings, approved_path: Path) -> Path:
    """Verifica o estado de categorização — o trabalho é feito pelo agente."""
    approved_path = approved_path.resolve()
    questions = load_questions(approved_path)

    pending = [q for q in questions if _needs_categorization(q)]
    done = sum(1 for q in questions if not _needs_categorization(q))
    total = len(questions)

    if pending:
        print(f"[categorize] {done}/{total} questões já categorizadas.")
        print(f"[categorize] {len(pending)} questão(ões) por categorizar:")
        for q in pending:
            print(f"  - {q.id_item}: {(q.enunciado or '')[:80]!r}")
        print("[categorize] ℹ️  A categorização deve ser feita pelo agente Claude Code")
        print("[categorize]    directamente no questoes_aprovadas.json (sem API externa).")
    else:
        print(f"[categorize] ✅ Todas as {total} questões já estão categorizadas.")

    dump_questions(approved_path, questions)
    print(f"[categorize] {done}/{total} questões categorizadas → {approved_path}")
    return approved_path
