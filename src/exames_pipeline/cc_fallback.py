"""
Módulo CC-Fallback — reextracção de critérios via agente Claude Code.

O fallback multimodal via API (Gemini Flash) foi removido.
A correcção de critérios deve ser feita pelo agente Claude Code
directamente com Read + Edit sobre criterios_aprovados.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import Settings
from .schemas import dump_criterios, load_criterios


def run_cc_fallback(
    settings: Settings,
    criterios_path: Path,
    revisao_path: Path,
    pdf_path: Path,
) -> Path:
    """Informa quais itens precisam de revisão manual pelo agente.

    O fallback automático via API foi descontinuado.
    O agente Claude Code deve corrigir os itens marcados directamente
    em criterios_aprovados.json usando Read + Edit.
    """
    criterios_path = criterios_path.resolve()
    revisao_path   = revisao_path.resolve()

    revisao = json.loads(revisao_path.read_text(encoding="utf-8"))

    if "bullets_para_fallback" in revisao:
        bullets_map: dict = revisao["bullets_para_fallback"]
    else:
        bullets_map = {iid: [] for iid in revisao.get("itens_para_fallback", [])}

    if not bullets_map:
        print("[cc_fallback] ℹ️  Nenhum bullet marcado para revisão.")
        return criterios_path

    print(f"[cc_fallback] ⚠️  {len(bullets_map)} item(ns) marcado(s) para revisão:")
    for id_item, bullet_idxs in bullets_map.items():
        suffix = f" bullets {bullet_idxs}" if bullet_idxs else " (item completo)"
        print(f"  - {id_item}{suffix}")
    print("[cc_fallback]    O agente Claude Code deve corrigir estes itens em")
    print(f"[cc_fallback]    {criterios_path} com Read + Edit.")

    return criterios_path
