from __future__ import annotations

import re
from pathlib import Path

from .schemas import dump_json, dump_questions, load_questions

_ALTERNATIVES_IN_ENUNCIADO_PATTERN = re.compile(r"(?:^|\n)\s*\(A\)[\s\S]*$")
_ALT_PREFIX_RE = re.compile(r"^\(([A-D])\)\s*")


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for tag in tags:
        value = str(tag).strip()
        if not value:
            continue
        if not value.startswith("#"):
            value = f"#{value}"
        if value not in normalized:
            normalized.append(value)
    return normalized


def _count_unescaped_dollars(text: str) -> int:
    return len(re.findall(r"(?<!\\)\$", text or ""))


def run_micro_lint(raw_json_path: Path) -> Path:
    raw_json_path = raw_json_path.resolve()
    questions = load_questions(raw_json_path)
    report: list[dict] = []

    for question in questions:
        fixes: list[str] = []
        warnings: list[str] = []

        question.enunciado = re.sub(r"\n{3,}", "\n\n", (question.enunciado or "").strip())
        if question.alternativas:
            question.enunciado = _ALTERNATIVES_IN_ENUNCIADO_PATTERN.sub("", question.enunciado).strip()

        for alt in question.alternativas or []:
            alt.letra = (alt.letra or "").strip().upper()
            alt.texto = re.sub(r"\n{3,}", "\n\n", (alt.texto or "").strip())
            prefix = _ALT_PREFIX_RE.match(alt.texto)
            if prefix and prefix.group(1) == alt.letra:
                alt.texto = _ALT_PREFIX_RE.sub("", alt.texto).strip()
                fixes.append(f"alternativa {alt.letra}: removido prefixo duplicado")

        if len(question.alternativas or []) == 4:
            letters = [alt.letra for alt in question.alternativas]
            if sorted(letters) == ["A", "B", "C", "D"] and letters != ["A", "B", "C", "D"]:
                question.alternativas = sorted(question.alternativas, key=lambda alt: alt.letra)
                fixes.append("alternativas reordenadas para A-D")

        question.tags = _normalize_tags(question.tags or [])

        if _count_unescaped_dollars(question.enunciado) % 2 != 0:
            warnings.append("enunciado com delimitadores '$' desequilibrados")
        for alt in question.alternativas or []:
            if _count_unescaped_dollars(alt.texto) % 2 != 0:
                warnings.append(f"alternativa {alt.letra} com delimitadores '$' desequilibrados")

        normalized_alt_texts = [re.sub(r"\s+", " ", alt.texto).strip().lower() for alt in question.alternativas or []]
        non_empty = [text for text in normalized_alt_texts if text]
        if len(non_empty) != len(set(non_empty)):
            warnings.append("alternativas com texto duplicado após normalização")

        for fix in fixes:
            note = f"[micro-lint][corrigido] {fix}"
            if note not in question.observacoes:
                question.observacoes.append(note)
        for warning in warnings:
            note = f"[micro-lint][aviso] {warning}"
            if note not in question.observacoes:
                question.observacoes.append(note)

        report.append({"id_item": question.id_item, "fixes": fixes, "warnings": warnings})

    dump_questions(raw_json_path, questions)
    report_path = raw_json_path.parent / "questoes_micro_lint.json"
    dump_json(report_path, report)
    return report_path
