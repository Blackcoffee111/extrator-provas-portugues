"""
Módulo OCR Repair — detecta marcadores de questão mal reconhecidos pelo OCR.

A detecção automática de padrões problemáticos é mantida, mas a correcção
via API foi removida. O agente Claude Code deve corrigir o markdown
directamente com Read + Edit ao ver o PDF original.

Suporta dois perfis:
- Matemática A: deteção de marcadores de estrela LaTeX sem número.
- Português: deteção de diacríticos ausentes, notas de rodapé mal parseadas,
  numeração de linhas do excerto, e hífens de quebra de linha não removidos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


# ---------------------------------------------------------------------------
# Padrões comuns
# ---------------------------------------------------------------------------

_STAR_ALONE_RE = re.compile(r"^\s*\$\\(?:star|bigstar|ast)\b[^$\d]*\$\s*$")
_STAR_PARTIAL_NUM_RE = re.compile(r"^\s*\$\\(?:star|bigstar|ast)\b[^$]*\d[^$]*\$\s*$")

# ---------------------------------------------------------------------------
# Padrões específicos de Português
# ---------------------------------------------------------------------------

# Hífen de quebra de linha: palavra-\n"próxima" → "palavra-próxima" (só detecta)
_LINEBREAK_HYPHEN_RE = re.compile(r"\w-\s*\n\s*\w")

# Diacrítico de nota de rodapé colado ao texto: "cabelos2" → "cabelos²"
_NOTE_NUM_FUSED_RE = re.compile(r"([a-záàâãéêíóôõúç])(\d)(?=\s)")

# Numeração de linha do excerto sem espaço: "5calamistrar" → detectar
_LINE_NUM_FUSED_RE = re.compile(r"(?m)^(\d{1,3})([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][a-záàâãéêíóôõúç])")

# Aspas inglesas que deviam ser «»: "text" sem LaTeX próximo
_STRAIGHT_QUOTES_RE = re.compile(r'(?<![`$])"[^"\n]{3,}"(?![`$])')


@dataclass
class _OcrIssue:
    line_index: int
    issue_type: str
    search_text: str


def detect_ocr_issues(markdown_text: str) -> list[_OcrIssue]:
    """Detecta linhas com marcador de questão sem número reconhecível (Matemática A)."""
    lines = markdown_text.splitlines()
    jobs: list[_OcrIssue] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if _STAR_ALONE_RE.match(stripped):
            issue_type = "star_no_number"
        elif _STAR_PARTIAL_NUM_RE.match(stripped):
            issue_type = "star_partial_number"
        else:
            continue

        context_words: list[str] = []
        for ctx_line in lines[i + 1 : i + 4]:
            words = re.findall(r"[A-Za-záàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ]{4,}", ctx_line)
            context_words.extend(words)
            if len(context_words) >= 4:
                break

        search_text = " ".join(context_words[:4])
        if not search_text:
            continue

        jobs.append(_OcrIssue(line_index=i, issue_type=issue_type, search_text=search_text))

    return jobs


def detect_ocr_issues_portugues(markdown_text: str) -> list[_OcrIssue]:
    """Detecta problemas típicos de OCR em provas de Português."""
    lines = markdown_text.splitlines()
    jobs: list[_OcrIssue] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if _LINEBREAK_HYPHEN_RE.search(stripped):
            jobs.append(_OcrIssue(i, "linebreak_hyphen",
                                  stripped[:60]))
        if _NOTE_NUM_FUSED_RE.search(stripped):
            jobs.append(_OcrIssue(i, "note_number_fused",
                                  stripped[:60]))
        if _LINE_NUM_FUSED_RE.match(stripped):
            jobs.append(_OcrIssue(i, "line_number_fused",
                                  stripped[:60]))
        if _STRAIGHT_QUOTES_RE.search(stripped):
            jobs.append(_OcrIssue(i, "straight_quotes",
                                  stripped[:60]))

    return jobs


def repair_ocr_markers(
    settings: Settings,
    pdf_path: Path,
    markdown_path: Path,
    materia: str = "",
) -> bool:
    """Detecta marcadores OCR defeituosos e reporta ao agente.

    Retorna sempre False (nenhuma correcção automática aplicada).
    """
    if not markdown_path.exists():
        return False

    markdown_text = markdown_path.read_text(encoding="utf-8")

    is_pt = "portugu" in (materia or "").lower() or "portugu" in str(markdown_path).lower()

    if is_pt:
        jobs = detect_ocr_issues_portugues(markdown_text)
        label = "problema(s) OCR Português"
    else:
        jobs = detect_ocr_issues(markdown_text)
        label = "marcador(es) suspeito(s)"

    if not jobs:
        return False

    print(f"[ocr_repair] ⚠️  {len(jobs)} {label} detectado(s):")
    for job in jobs:
        print(f"  linha {job.line_index + 1}: {job.issue_type!r} — {job.search_text!r}")
    print("[ocr_repair]    O agente Claude Code deve corrigir o markdown com Read + Edit.")
    return False
