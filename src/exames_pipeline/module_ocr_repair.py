"""
Módulo OCR Repair — detecta marcadores de questão mal reconhecidos pelo OCR.

A detecção automática de padrões problemáticos é mantida, mas a correcção
via API (Gemini) foi removida. O agente Claude Code deve corrigir o markdown
directamente com Read + Edit ao ver o PDF original.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings


# ---------------------------------------------------------------------------
# Padrões de detecção (após normalizações básicas)
# ---------------------------------------------------------------------------

# Linha que contém APENAS uma estrela LaTeX sem número: "$\star$", "$\bigstar$", "$\ast$"
_STAR_ALONE_RE = re.compile(
    r"^\s*\$\\(?:star|bigstar|ast)\b[^$\d]*\$\s*$"
)

# Número parcialmente dentro de bloco LaTeX com estrela (A2/C2 residual):
_STAR_PARTIAL_NUM_RE = re.compile(
    r"^\s*\$\\(?:star|bigstar|ast)\b[^$]*\d[^$]*\$\s*$"
)


@dataclass
class _CropJob:
    line_index: int
    issue_type: str          # "star_no_number" | "star_partial_number"
    search_text: str


def detect_ocr_issues(markdown_text: str) -> list[_CropJob]:
    """Detecta linhas com marcador de questão sem número reconhecível."""
    lines = markdown_text.splitlines()
    jobs: list[_CropJob] = []

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

        jobs.append(_CropJob(
            line_index=i,
            issue_type=issue_type,
            search_text=search_text,
        ))

    return jobs


def repair_ocr_markers(
    settings: Settings,
    pdf_path: Path,
    markdown_path: Path,
) -> bool:
    """Detecção de marcadores OCR defeituosos — correcção via API removida.

    Se existirem marcadores problemáticos, reporta-os para que o agente
    Claude Code os corrija manualmente com Read + Edit no PDF original.

    Retorna sempre False (nenhuma correcção automática aplicada).
    """
    if not markdown_path.exists():
        return False

    markdown_text = markdown_path.read_text(encoding="utf-8")
    jobs = detect_ocr_issues(markdown_text)

    if not jobs:
        return False

    print(f"[ocr_repair] ⚠️  {len(jobs)} marcador(es) suspeito(s) detectado(s):")
    for job in jobs:
        print(f"  linha {job.line_index + 1}: {job.issue_type!r} — contexto: {job.search_text!r}")
    print("[ocr_repair]    O agente Claude Code deve corrigir o markdown com Read + Edit.")
    return False
