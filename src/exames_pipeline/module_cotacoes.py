from __future__ import annotations

import re
from pathlib import Path

from .config import Settings
from .schemas import EstruturaCotacoes, dump_cotacoes
from .utils import IMAGE_PATTERN


COTACOES_HEADING_PATTERN = re.compile(
    r"(?m)^#{0,3}\s*COTA[ÇC][ÕO]ES\b",
    re.IGNORECASE,
)

_GROUP_RE = re.compile(r"GRUPO\s+(I{1,3}V?|VI*)", re.IGNORECASE)
_PARTE_RE = re.compile(r"PARTE\s+([A-C])", re.IGNORECASE)
_RANGE_RE = re.compile(r"^(?:#\s*)?(\d+)\.\s+a\s+(\d+)", re.IGNORECASE)
_TIMES_RE = re.compile(r"(\d+)\s*(?:\\times|[×x])\s*(\d+)", re.IGNORECASE)
_ITEM_RE = re.compile(r"^(?:[#*\s]*)?(\d+(?:\.\d+)*)\.?\s+(\d+)\s*pontos?", re.IGNORECASE)
# Linha de item com coluna (tabela MD): "| 1. | 2. | 4. | 5. | 7. |"
_TABLE_HEADER_RE = re.compile(r"^\|(?:\s*[\d.]+\s*\|)+")
# Linha de cotação tabular: "| 13 | 13 | 13 | 13 | 13 |"
_TABLE_SCORES_RE = re.compile(r"^\|(?:\s*\d+\s*\|)+")
# Linha de pool opcional: "Destes 5 itens, contribuem para a classificação ... os 3 itens"
_POOL_OPCIONAL_RE = re.compile(
    r"(?:Destes|dos restantes)\s+(\d+)\s+itens.*?contribuem.*?os\s+(\d+)\s+itens",
    re.IGNORECASE | re.DOTALL,
)


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
    """Parseia a secção de cotações a partir de texto extraído pelo OCR, sem LLM.

    Suporta dois formatos:
    - Formato Matemática A: "GRUPO I", itens por linha, "1. a 8... 8 × 5 pontos"
    - Formato Português: tabela Markdown com itens em cabeçalho e pontuações na linha seguinte,
      mais possível secção de pools opcionais.
    """
    current_group = ""
    current_parte = ""
    cotacoes: dict[str, int] = {}
    estrutura: dict[str, list[str]] = {}
    # Estado temporário: por grupo, quantos itens contam ("escolher") declarados pelo texto.
    _pending_pool_count: dict[str, int] = {}
    # Estado temporário: por grupo, soma de pontos do pool quando o texto a indica.
    _pending_pool_pontos: dict[str, int] = {}

    def make_id(num_str: str) -> str:
        prefix = current_group
        if current_parte:
            prefix = f"{current_group}-{current_parte}" if current_group else current_parte
        return f"{prefix}-{num_str}" if prefix else num_str

    def add_item(item_id: str, pts: int) -> None:
        cotacoes[item_id] = pts
        numeric_part = item_id.split("-")[-1]
        if "." in numeric_part:
            parent_id = item_id.rsplit(".", 1)[0]
            estrutura.setdefault(parent_id, [])
            if item_id not in estrutura[parent_id]:
                estrutura[parent_id].append(item_id)
        else:
            estrutura.setdefault(item_id, [])

    lines = after_heading.split("\n")
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.strip()
        i += 1

        if not line:
            continue

        # Pool opcional: "Destes 5 itens, contribuem ... os 3 itens"
        pool_m = _POOL_OPCIONAL_RE.search(line)
        if pool_m:
            pool_key = current_group or "GLOBAL"
            _pending_pool_count[pool_key] = int(pool_m.group(2))  # quantos contam
            continue

        # Grupo heading: "# GRUPO I", "GRUPO II", etc.
        g = _GROUP_RE.search(line)
        if g and ("GRUPO" in line.upper()):
            current_group = g.group(1).upper()
            current_parte = ""
            continue

        # PARTE heading: "PARTE A", "Parte B", etc.
        p = _PARTE_RE.search(line)
        if p and "PARTE" in line.upper():
            current_parte = p.group(1).upper()
            continue

        # Tabela MD de cabeçalho de itens: "| 1. | 2. | 4. | 5. | 7. |"
        if _TABLE_HEADER_RE.match(line):
            header_cells = [c.strip().rstrip(".") for c in line.split("|") if c.strip()]
            # Próxima linha não vazia — separador ou pontuações
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines):
                continue
            next_line = lines[i].strip()
            i += 1
            # Pular linha separadora de tabela MD ("| --- | --- |")
            if re.match(r"^\|[-|\s:]+\|", next_line):
                while i < len(lines) and not lines[i].strip():
                    i += 1
                if i >= len(lines):
                    continue
                next_line = lines[i].strip()
                i += 1

            if _TABLE_SCORES_RE.match(next_line):
                score_cells = [c.strip() for c in next_line.split("|") if c.strip()]
                for header, score in zip(header_cells, score_cells):
                    if header.isdigit() and score.isdigit():
                        add_item(make_id(header), int(score))
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
            for j in range(start, end + 1):
                add_item(make_id(str(j)), per_item)
            continue

        # Item simples: "2.1. 10 pontos" ou "# 3.1. 15 pontos"
        m = _ITEM_RE.match(line)
        if m:
            item_num = m.group(1)
            pts = int(m.group(2))
            add_item(make_id(item_num), pts)

    if not cotacoes:
        return None

    # Construir lista de pools opcionais no formato canónico
    pool_opcional: list[dict] = []
    for grp, escolher in _pending_pool_count.items():
        grp_prefix = "" if grp == "GLOBAL" else f"{grp}-"
        itens_do_grupo = [
            k for k in estrutura
            if (not grp_prefix or k.startswith(grp_prefix))
            and "." not in k.split("-")[-1]
        ]
        if not itens_do_grupo:
            continue
        pool_opcional.append({
            "pontos": _pending_pool_pontos.get(grp),
            "itens": sorted(itens_do_grupo),
            "escolher": escolher,
        })

    top_level = sum(1 for k in estrutura if "." not in k.split("-")[-1])
    return EstruturaCotacoes(
        total_itens_principais=top_level,
        estrutura=estrutura,
        cotacoes=cotacoes,
        confianca="alta",
        raw_response="",
        pool_opcional=pool_opcional,
    )


def extract_cotacoes_estrutura(settings: Settings, markdown_path: Path) -> Path | None:
    """Extrai o manifesto estrutural a partir da secção COTAÇÕES do prova.md.

    O ficheiro `cotacoes_estrutura.json` declara o **conjunto canónico de IDs
    de itens** que o exame contém. Os pontos são metadados; o que é validado
    contra o JSON estruturado é a estrutura (presença/ausência/agrupamento).

    Falha-alto: quando o parser não consegue extrair nada utilizável, retorna
    None **e não cria o ficheiro**. O `validate` bloqueará explicitamente até
    que o ficheiro exista no formato canónico — manualmente ou via re-extract.
    """
    markdown_path = markdown_path.resolve()
    if not markdown_path.exists():
        return None

    markdown_text = markdown_path.read_text(encoding="utf-8")

    match = COTACOES_HEADING_PATTERN.search(markdown_text)
    if not match:
        print("[cotacoes] ⚠️  Secção '# COTAÇÕES' não encontrada no prova.md.")
        print("[cotacoes]    O 'validate' bloqueará até cotacoes_estrutura.json existir no formato canónico.")
        return None

    after_heading = markdown_text[match.end():]

    cotacoes = _parse_cotacoes_from_text(after_heading)
    if cotacoes is not None:
        output_path = markdown_path.parent / "cotacoes_estrutura.json"
        dump_cotacoes(output_path, cotacoes)
        ids = sorted(cotacoes.cotacoes.keys())
        print(f"[cotacoes] ✅ Manifesto estrutural extraído ({len(ids)} itens) → {output_path}")
        if cotacoes.pool_opcional:
            for pool in cotacoes.pool_opcional:
                print(f"[cotacoes]    Pool opcional: escolher {pool['escolher']} de {len(pool['itens'])} → {pool['itens']}")
        return output_path

    # Parser falhou — diagnóstico claro, sem stub silencioso.
    image_match = IMAGE_PATTERN.search(after_heading)
    print("=" * 70)
    print("  [cotacoes] PARSER FALHOU — cotacoes_estrutura.json NÃO foi criado")
    print("=" * 70)
    if image_match:
        print("  Causa provável: secção COTAÇÕES contém imagem (sem texto parseável).")
    else:
        print("  Causa provável: tabela com formato inesperado ou OCR corrompido.")
    print("  Acção:")
    print("    1. Abrir o PDF na página da tabela de cotações.")
    print(f"    2. Criar manualmente {markdown_path.parent / 'cotacoes_estrutura.json'}")
    print("       no formato canónico:")
    print("         {\"cotacoes\": {\"I-1\": 13, ...}, \"estrutura\": {\"I-1\": [], ...},")
    print("          \"total_itens_principais\": N, \"confianca\": \"alta\"}")
    print("    3. Re-correr `run_stage(stage='validate')`.")
    print("=" * 70)
    return None
