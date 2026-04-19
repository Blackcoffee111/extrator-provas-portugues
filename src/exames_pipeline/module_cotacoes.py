from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import Settings
from .schemas import EstruturaCotacoes, dump_cotacoes
from .utils import IMAGE_PATTERN


COTACOES_HEADING_PATTERN = re.compile(
    r"(?m)^#{0,3}\s*COTA[ÇC][ÕO]ES\b",
    re.IGNORECASE,
)

_GROUP_RE = re.compile(r"GRUPO\s+(I{1,3}V?|VI*)", re.IGNORECASE)
_RANGE_RE = re.compile(r"^(?:#\s*)?(\d+)\.\s+a\s+(\d+)", re.IGNORECASE)
_TIMES_RE = re.compile(r"(\d+)\s*(?:\\times|[×x])\s*(\d+)", re.IGNORECASE)
_ITEM_RE = re.compile(r"^(?:[#*\s]*)?(\d+(?:\.\d+)*)\.?\s+(\d+)\s*pontos?", re.IGNORECASE)


def _fix_collapsed_group_format(estrutura: dict[str, list[str]]) -> dict[str, list[str]]:
    """Corrige o formato onde o modelo colapsa todos os itens de um grupo num só pai."""
    new_estrutura: dict[str, list[str]] = {}

    for key, children in estrutura.items():
        if key in children:
            parents_of: dict[str, list[str]] = {}
            leaves: list[str] = []
            for child in children:
                if "." in child:
                    parent = child.rsplit(".", 1)[0]
                    parents_of.setdefault(parent, []).append(child)
                else:
                    leaves.append(child)

            for leaf in leaves:
                if leaf in parents_of:
                    new_estrutura[leaf] = parents_of[leaf]
                else:
                    new_estrutura[leaf] = []
        else:
            new_estrutura[key] = children

    return new_estrutura


def _parse_cotacoes_from_text(after_heading: str) -> EstruturaCotacoes | None:
    """Parseia a secção de cotações a partir de texto extraído pelo OCR, sem LLM."""
    current_group = ""
    cotacoes: dict[str, int] = {}
    estrutura: dict[str, list[str]] = {}

    def make_id(num_str: str) -> str:
        return f"{current_group}-{num_str}" if current_group else num_str

    def add_item(item_id: str, pts: int) -> None:
        cotacoes[item_id] = pts
        numeric_part = item_id.split("-")[-1]
        if "." in numeric_part:
            # Subitem → adicionar como filho do pai, NÃO como chave de topo
            parent_id = item_id.rsplit(".", 1)[0]
            estrutura.setdefault(parent_id, [])
            if item_id not in estrutura[parent_id]:
                estrutura[parent_id].append(item_id)
        else:
            # Item de topo-nível
            estrutura.setdefault(item_id, [])

    for raw_line in after_heading.split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        # Grupo heading: "# GRUPO I", "# GRUPO II", etc.
        g = _GROUP_RE.search(line)
        if g and ("#" in line or "GRUPO" in line.upper()):
            current_group = g.group(1).upper()
            continue

        # Range: "1. a 8... 8 × 5 pontos"
        r = _RANGE_RE.match(line)
        if r:
            start, end = int(r.group(1)), int(r.group(2))
            t = _TIMES_RE.search(line)
            if t:
                per_item = int(t.group(2))
            else:
                pts_m = re.search(r"(\d+)\s*pontos?", line, re.IGNORECASE)
                total = int(pts_m.group(1)) if pts_m else 0
                count = end - start + 1
                per_item = total // count if count else 0
            for i in range(start, end + 1):
                add_item(make_id(str(i)), per_item)
            continue

        # Item simples: "2.1. 10 pontos" ou "# 3.1. 15 pontos"
        m = _ITEM_RE.match(line)
        if m:
            item_num = m.group(1)
            pts = int(m.group(2))
            add_item(make_id(item_num), pts)

    if not cotacoes:
        return None

    top_level = sum(1 for k in estrutura if "." not in k.split("-")[-1])
    return EstruturaCotacoes(
        total_itens_principais=top_level,
        estrutura=estrutura,
        cotacoes=cotacoes,
        confianca="alta",
    )


def extract_cotacoes_estrutura(settings: Settings, markdown_path: Path) -> Path | None:
    """Extrai a estrutura da prova a partir da secção de cotações.

    Estratégia:
    1. Tenta parsear o texto da secção # COTAÇÕES directamente (sem LLM).
    2. Se o texto não for suficiente (cotações como imagem), usa o LLM configurado.
    """
    markdown_path = markdown_path.resolve()
    if not markdown_path.exists():
        return None

    markdown_text = markdown_path.read_text(encoding="utf-8")

    match = COTACOES_HEADING_PATTERN.search(markdown_text)
    if not match:
        return None

    after_heading = markdown_text[match.end():]

    # --- Tentativa 1: parser de texto (sem LLM) ---
    cotacoes = _parse_cotacoes_from_text(after_heading)
    if cotacoes is not None:
        output_path = markdown_path.parent / "cotacoes_estrutura.json"
        dump_cotacoes(output_path, cotacoes)
        print(f"[cotacoes] ✅ Estrutura extraída por parser de texto → {output_path}")
        return output_path

    # Se o parser de texto falhou e a secção tem imagem, o agente deve
    # criar o cotacoes_estrutura.json manualmente com Read + Edit.
    image_match = IMAGE_PATTERN.search(after_heading)
    if image_match:
        print("[cotacoes] ⚠️  Secção COTAÇÕES contém imagem — parser de texto insuficiente.")
        print("[cotacoes]    O agente Claude Code deve criar cotacoes_estrutura.json manualmente.")
    else:
        print("[cotacoes] ⚠️  Secção COTAÇÕES sem texto parseable e sem imagem.")
    return None
