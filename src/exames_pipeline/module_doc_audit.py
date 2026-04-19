"""Módulo 2.5 — Auditoria de questões (descontinuado).

O trabalho de auditoria/revisão é feito pelo agente Claude Code directamente
usando as ferramentas Read + Edit. Não são feitas chamadas a APIs externas.
"""
from __future__ import annotations

from pathlib import Path

from .config import Settings


def run_doc_audit(
    settings: Settings,
    markdown_path: Path,
    workspace_dir: Path | None = None,
) -> Path:
    """Stub — auditoria via API descontinuada.

    A revisão deve ser feita pelo agente Claude Code directamente
    lendo questoes_raw.json e editando os itens (setar reviewed:true).
    """
    raise NotImplementedError(
        "run_doc_audit foi descontinuado. "
        "A revisão de questões é feita pelo agente Claude Code directamente "
        "(ferramentas Read + Edit sobre questoes_raw.json)."
    )
