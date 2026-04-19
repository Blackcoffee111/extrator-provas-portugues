from __future__ import annotations

import re
from pathlib import Path

from .schemas import dump_json, dump_questions, load_questions

_ALTERNATIVES_IN_ENUNCIADO_PATTERN = re.compile(r"(?:^|\n)\s*\(A\)[\s\S]*$")
_ALT_PREFIX_RE = re.compile(r"^\(([A-D])\)\s*")

# Regras tipográficas PT
_TRIPLE_NEWLINE_RE = re.compile(r"\n{3,}")
_STRAIGHT_DOUBLE_QUOTES_RE = re.compile(r'(?<!\$)"([^"\n]+)"(?!\$)')
_MISSING_ACCENT_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # "nao" isolado que devia ser "não" — apenas quando circundado por espaços e não em LaTeX
    (re.compile(r'(?<![`$\w])nao(?![`$\w])'), "nao", "não"),
]


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


def _lint_portugues(enunciado: str) -> tuple[str, list[str], list[str]]:
    """Aplica fixes tipográficos específicos de Português. Devolve (texto, fixes, warnings)."""
    fixes: list[str] = []
    warnings: list[str] = []
    text = enunciado

    # Normalizar aspas retas para «» (só fora de blocos LaTeX/código)
    def _replace_quotes(m: re.Match) -> str:
        return f"«{m.group(1)}»"

    new_text = _STRAIGHT_DOUBLE_QUOTES_RE.sub(_replace_quotes, text)
    if new_text != text:
        fixes.append("aspas retas convertidas para «»")
        text = new_text

    # Reticências
    new_text = re.sub(r'(?<!\.)\.\.\.(?!\.)', '…', text)
    if new_text != text:
        fixes.append("reticências normalizadas para …")
        text = new_text

    # Hífen de quebra de linha: "pala-\nvra" → "palavra" (só se não for hífen semântico)
    def _fix_linebreak_hyphen(m: re.Match) -> str:
        return m.group(0).replace("-\n", "")
    new_text = re.sub(r'([a-záàâãéêíóôõúç])-\n([a-záàâãéêíóôõúç])', _fix_linebreak_hyphen, text)
    if new_text != text:
        fixes.append("hífens de quebra de linha removidos")
        text = new_text

    # Aviso: aspas «» sem fechar
    open_count = text.count("«")
    close_count = text.count("»")
    if open_count != close_count:
        warnings.append(f"aspas «» desequilibradas: {open_count} abrir, {close_count} fechar")

    return text, fixes, warnings


def run_micro_lint(raw_json_path: Path, materia: str = "") -> Path:
    raw_json_path = raw_json_path.resolve()
    questions = load_questions(raw_json_path)
    report: list[dict] = []

    is_pt = "portugu" in (materia or "").lower()
    # Auto-detectar pelo caminho se matéria não passada
    if not is_pt:
        is_pt = "portugu" in str(raw_json_path).lower()

    for question in questions:
        fixes: list[str] = []
        warnings: list[str] = []

        question.enunciado = _TRIPLE_NEWLINE_RE.sub("\n\n", (question.enunciado or "").strip())
        if question.alternativas:
            question.enunciado = _ALTERNATIVES_IN_ENUNCIADO_PATTERN.sub("", question.enunciado).strip()

        # Tipografia PT
        if is_pt and question.enunciado:
            question.enunciado, pt_fixes, pt_warnings = _lint_portugues(question.enunciado)
            fixes.extend(pt_fixes)
            warnings.extend(pt_warnings)

        for alt in question.alternativas or []:
            alt.letra = (alt.letra or "").strip().upper()
            alt.texto = _TRIPLE_NEWLINE_RE.sub("\n\n", (alt.texto or "").strip())
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

        # Verificação LaTeX (só Matemática)
        if not is_pt:
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
