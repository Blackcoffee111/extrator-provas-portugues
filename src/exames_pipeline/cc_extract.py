"""
Módulo CC-Extract — Extrai critérios de classificação do markdown CC-VD.

Workflow esperado:
  1. Correr `exames_pipeline extract <cc_pdf> --no-preprocess` para gerar o markdown via MinerU.
  2. Correr `exames_pipeline cc-extract <cc.md> [--fonte "..."]` para estruturar os critérios.

Este módulo é independente do pipeline de extração de questões.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .cc_ocr_lint import lint_criterios
from .config import Settings
from .schemas import CriterioRaw, dump_criterios, dump_json
from .utils import infer_fonte_from_path


# ── Padrões de segmentação ─────────────────────────────────────────────────────

# Âncora para ignorar os Critérios Gerais.
# Tenta primeiro o heading explícito; se não existir (MinerU pode não o gerar)
# cai de volta ao primeiro cabeçalho de item "1. X pontos".
_CRITERIOS_ESPECIFICOS_RE = re.compile(
    r'(?i)CRIT[ÉE]RIOS\s+ESPEC[ÍI]FICOS\s+DE\s+CLASSIFICA[ÇC][ÃA]O'
)
_FIRST_ITEM_RE = re.compile(r'(?m)^#{0,4}\s*1\.[ \t]+\d+\s*pontos')
_COTACOES_TRUNCATE_RE = re.compile(r'(?m)^#{0,4}\s*COTA[ÇC][ÕO]ES\b', re.IGNORECASE)
# Heading de grupo no markdown CC: "# GRUPO I", "## GRUPO II", etc.
_GROUP_HEADING_RE = re.compile(r'(?m)^#{1,4}\s*GRUPO\s+([IVX]+)\b', re.IGNORECASE)

# Cabeçalho de item no markdown gerado pelo MinerU:
#   "1. 12 pontos Opção (C)"   →  MC numa só linha
#   "2. 14 pontos"             →  aberta, conteúdo nas linhas seguintes
#   "# 3. 14 pontos"           →  com prefixo de heading markdown
#   "4.1. 14 pontos"           →  subitem
#   "5.1. . 14 pontos"         →  ponto extra entre ID e cotação (OCR 2024)
# Não existem dot-leaders no output do MinerU; o conteúdo pode continuar na mesma linha.
_ITEM_HEADER_RE = re.compile(
    r'(?m)^#{0,4}\s*(\d{1,2}(?:\.\d+)?)\.(?:[ \t]*\.)?[ \t]+(\d+)\s*pontos'
)

# Deteção secundária: linha com ID seguido de texto (pontos não são imediatos).
# Ex: "3.1. Concluir que o raio é 1 2 pontos Escrever a condição..."
# O ID é capturado; a cotação total é inferida das cotações quando disponível.
_ITEM_HEADER_INLINE_RE = re.compile(
    r'(?m)^#{0,4}\s*(\d{1,2}(?:\.\d+)?)\.\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]'
)
_IMPLICIT_POINTS_HEADER_RE = re.compile(r'(?m)^#{0,4}\s*(\d+)\s*pontos\s*$')

# Detecção de resposta de escolha múltipla
# Caso 1: "Opção (C)" em qualquer posição no bloco
_MC_ANSWER_RE = re.compile(r'Op[çc][aã]o\s*\(\s*([A-D])\s*\)', re.IGNORECASE)
# Caso 2: "(C)" isolado numa linha (sem "Opção") — comum em CC-VD 2024
_MC_BARE_ANSWER_RE = re.compile(r'(?m)^[ \t]*\(\s*([A-D])\s*\)[ \t]*$')

# Multi-select PT: deteção de respostas no formato "(I)(III)(IV)" ou "I, III, IV"
# Procura sequências de algarismos romanos I-V, opcionalmente entre parêntesis,
# separadas por vírgulas, " e ", ou justapostos.
_MULTI_SELECT_ROMAN_RE = re.compile(
    r'\(?\b(I{1,3}|IV|V)\b\)?'
)

# Referências a imagens no markdown: ![alt](path)
_IMAGE_REF_RE = re.compile(r'!\[.*?\]\(([^)]+)\)')


# ── Parsing por regex (sem LLM) ────────────────────────────────────────────────

# Separador de processos alternativos: "1.º Processo", "2.º Processo", etc.
_PROCESS_SEP_RE = re.compile(r'\d+\.º\s+Processo', re.IGNORECASE)

# Separador de secção de notas: "# Notas:", "Notas:", "Nota:" no início de linha
_NOTES_SECTION_RE = re.compile(r'(?m)^#{0,3}\s*Nota[s]?:', re.IGNORECASE)


def _strip_notes_section(text: str) -> str:
    """Remove a secção de Notas e tudo o que se segue."""
    m = _NOTES_SECTION_RE.search(text)
    return text[:m.start()].strip() if m else text


def _parse_steps(text: str) -> list[dict]:
    """
    Extrai etapas do formato "Descrição da etapa  N pontos".
    Remove a secção de Notas antes de parsear.
    """
    clean = _strip_notes_section(text)

    # Dividir por ocorrências de "N ponto(s)"
    parts = re.split(r'\b(\d+)\s+pont[oa]s?\b', clean)
    # parts = [desc0, pts0, desc1, pts1, ...]
    steps = []
    for i in range(0, len(parts) - 1, 2):
        desc = parts[i].strip(' \t\n\r.,;')
        if desc:
            steps.append({"pontos": int(parts[i + 1]), "descricao": desc})
    if steps:
        return steps

    bullets = [
        line.strip().lstrip("•").strip()
        for line in clean.splitlines()
        if line.strip().startswith("•")
    ]
    if bullets:
        return [{"pontos": 0, "descricao": bullet} for bullet in bullets if bullet]
    return steps


def _parse_open_criteria(block: str) -> tuple[list[dict], list[str], str]:
    """
    Extrai critérios de um item de resposta aberta usando apenas regex.
    Suporta múltiplos processos separados por "N.º Processo".
    Retorna (criterios_parciais, resolucoes_alternativas, contexto).

    Quando existem separadores de processo:
    - Os steps top-level (antes do 1.º Processo) são extraídos normalmente.
    - O último step top-level recebe o texto integral do 1.º Processo agregado
      na sua `descricao`, incluindo o texto de transição ("Esta etapa pode ser
      resolvida por, pelo menos, dois processos.") e os sub-passos do processo.
    - Os processos alternativos (2.º, 3.º…) continuam em `resolucoes_alternativas`.
    Isto garante que os critérios parciais contêm o conteúdo integral até ao fim
    do 1.º Processo, sem sumarização.
    """
    process_matches = list(_PROCESS_SEP_RE.finditer(block))

    def _attach_p1_to_last_step(
        pre_text: str,
        p1_label: str,
        p1_text: str,
    ) -> list[dict]:
        """
        Analisa os steps top-level de `pre_text` e agrega o texto completo do
        1.º Processo ao último step. O texto de transição entre o último marker
        de pontos e o início do 1.º Processo (ex: "Esta etapa pode ser resolvida
        por, pelo menos, dois processos.") é incluído.
        """
        top_steps = _parse_steps(pre_text)
        if not top_steps:
            # Sem steps no pré-texto: usar os sub-passos do 1.º Processo directamente
            return _parse_steps(p1_text)

        # Texto de transição: tudo o que fica após o último "N pontos" em pre_text
        pts_markers = list(re.finditer(r'\b\d+\s+pont[oa]s?\b', pre_text))
        if pts_markers:
            transition = pre_text[pts_markers[-1].end():].strip()
        else:
            transition = ""

        p1_full = p1_label.strip()
        if p1_text.strip():
            p1_full += "\n" + p1_text.strip()

        last = top_steps[-1]
        parts = [last["descricao"]]
        if transition:
            parts.append(transition)
        parts.append(p1_full)
        last["descricao"] = "\n\n".join(parts)
        return top_steps

    if len(process_matches) >= 2:
        pre_text = block[:process_matches[0].start()]
        p1_label = block[process_matches[0].start():process_matches[0].end()]
        p1_text  = block[process_matches[0].end():process_matches[1].start()]
        criterios_parciais = _attach_p1_to_last_step(pre_text, p1_label, p1_text)
        # Processos alternativos: texto de cada processo a partir do 2.º
        resolucoes_alternativas = []
        for j in range(1, len(process_matches)):
            start = process_matches[j].start()
            end = process_matches[j + 1].start() if j + 1 < len(process_matches) else len(block)
            resolucoes_alternativas.append(block[start:end].strip())
        contexto = ""
    elif len(process_matches) == 1:
        pre_text = block[:process_matches[0].start()]
        p1_label = block[process_matches[0].start():process_matches[0].end()]
        p1_text  = block[process_matches[0].end():]
        criterios_parciais = _attach_p1_to_last_step(pre_text, p1_label, p1_text)
        resolucoes_alternativas = []
        contexto = ""
    else:
        contexto = ""
        criterios_parciais = _parse_steps(block)
        resolucoes_alternativas = []

    return criterios_parciais, resolucoes_alternativas, contexto


def _extract_mc_preamble_map(preamble: str) -> dict[str, str]:
    """
    Varre o preâmbulo (critérios gerais) à procura de padrões MC fora dos blocos de item.
    Ex: '5.1. Opção (B)' → {'5.1': 'B'}
    Usado como fallback para itens cujo 'Opção (X)' não ficou na mesma linha do cabeçalho.
    """
    pattern = re.compile(
        r'\b(\d{1,2}(?:\.\d+)?)\.?\s+Op[çcÇC][aãAÃ]o\s*\(\s*([A-D])\s*\)',
        re.IGNORECASE,
    )
    return {m.group(1): m.group(2).upper() for m in pattern.finditer(preamble)}


# ── Estrutura interna ──────────────────────────────────────────────────────────

@dataclass
class _CCBlock:
    id_item: str
    cotacao: int
    text: str
    offset: int = 0   # posição inicial do bloco no texto original (para lookup de grupo)


# ── Auto-correções LaTeX de alta confiança (Matemática A) ────────────────────

_AUTO_CORRECTIONS_MATH: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r'\\frac\s+\{'),   r'\\frac{',  'espaço espúrio em \\frac'),
    (re.compile(r'\\sqrt\s+\{'),   r'\\sqrt{',  'espaço espúrio em \\sqrt'),
    (re.compile(r'\\left\s+\('),   r'\\left(',  'espaço espúrio em \\left('),
    (re.compile(r'\\left\s+\['),   r'\\left[',  'espaço espúrio em \\left['),
    (re.compile(r'\\right\s+\)'),  r'\\right)', 'espaço espúrio em \\right)'),
    (re.compile(r'\\right\s+\]'),  r'\\right]', 'espaço espúrio em \\right]'),
    (re.compile(r'(?<!\$)(?<![a-zA-Z]) ([,\.])'), r'\1', 'espaço antes de pontuação'),
    (re.compile(r'(?<![a-zA-Z\\])ight(?=\s*[\(\)\[\]|.\\])'), r'\\right', 'OCR ight→\\right'),
    (re.compile(r'(?<![a-zA-Z\\])rac(?=\{)'), r'\\frac', 'OCR rac→\\frac'),
    (re.compile(r'\\sen\b'), r'\\sin', '\\sen→\\sin'),
]

# Auto-correções tipográficas PT (CC de Português)
_AUTO_CORRECTIONS_PT: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r'(?<!\$)(?<![a-zA-Z]) ([,\.])'), r'\1', 'espaço antes de pontuação'),
    (re.compile(r'\.\.\.'), '…', 'reticências normalizadas'),
]

# Deteção de níveis de desempenho PT: "Nível 5", "N5", "Nível N5", "nível 4 – ..."
_NIVEL_DESEMPENHO_RE = re.compile(
    r'(?i)n[íi]vel\s*(?:N\s*)?(\d)\b'
)
# Parâmetros de classificação PT (A, B, C com pontuação total)
_PARAMETRO_RE = re.compile(
    r'(?m)^#+\s*Par[âa]metro\s+([A-C])\b|^Par[âa]metro\s+([A-C])\b',
    re.IGNORECASE,
)


def _auto_correct(text: str, is_pt: bool = False) -> tuple[str, list[str]]:
    """Aplica correcções determinísticas de alta confiança antes do parse."""
    corrections = _AUTO_CORRECTIONS_PT if is_pt else _AUTO_CORRECTIONS_MATH
    fixes: list[str] = []
    for pattern, replacement, label in corrections:
        new_text = pattern.sub(replacement, text)
        if new_text != text:
            fixes.append(label)
            text = new_text
    return text, fixes


def _parse_niveis_desempenho(text: str) -> list[dict]:
    """Extrai níveis de desempenho PT: N5/N4/N3/N2/N1 com pontuações.

    Formato esperado no CC-VD:
    'Nível 5 (N5)  13 pontos  Texto do descritor...'
    ou
    'N5 – 13 pontos – Texto...'
    """
    niveis = []
    for match in re.finditer(
        r'[Nn][íi]vel\s*(?:[Nn]\s*)?(\d)\b[^\n]*?(\d+)\s*pont',
        text,
    ):
        nivel_num = int(match.group(1))
        pontos = int(match.group(2))
        # Extrair texto do descritor (até o próximo nível ou fim de parágrafo)
        start = match.end()
        end_match = re.search(r'\n[Nn][íi]vel\s*\d|\n\n', text[start:])
        descritor = text[start: start + end_match.start()].strip() if end_match else text[start:].strip()
        niveis.append({
            "nivel": f"N{nivel_num}",
            "pontos": pontos,
            "descritor": descritor[:300],
        })
    return niveis


# ── Dump compacto para revisão do agente ─────────────────────────────────────

_REVIEW_EXCLUDED = {"texto_original", "imagens", "fonte"}


def _dump_review_json(output_dir: Path, criterios: list[CriterioRaw]) -> Path:
    """Grava criterios_review.json sem texto_original e imagens.

    Este ficheiro é o que o agente deve ler primeiro — mais leve e focado
    nos campos editáveis. O texto_original fica acessível via get_cc_context().
    """
    compact = [
        {k: v for k, v in c.to_dict().items() if k not in _REVIEW_EXCLUDED}
        for c in criterios
    ]
    path = output_dir / "criterios_review.json"
    path.write_text(json.dumps(compact, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ── Funções auxiliares ─────────────────────────────────────────────────────────

def _find_criterios_especificos(markdown: str) -> str:
    """
    Retorna o texto a partir dos critérios específicos, ignorando os critérios gerais.
    Tenta o heading explícito primeiro; se não existir, usa o primeiro item '1. X pontos'.
    """
    m = _CRITERIOS_ESPECIFICOS_RE.search(markdown)
    if m:
        body = markdown[m.end():]
        cut = _COTACOES_TRUNCATE_RE.search(body)
        return body[:cut.start()].strip() if cut else body
    # Fallback: começa no primeiro item (MinerU não gera o heading explícito)
    m2 = _FIRST_ITEM_RE.search(markdown)
    if m2:
        body = markdown[m2.start():]
        cut = _COTACOES_TRUNCATE_RE.search(body)
        return body[:cut.start()].strip() if cut else body
    return markdown


def _segment_blocks(
    text: str,
    expected_cotacoes: dict[str, int] | None = None,
) -> list[_CCBlock]:
    """Divide o texto CC em blocos por cabeçalho de item.

    Primeiro tenta o padrão padrão "X.Y. N pontos".
    Se algum ID esperado (das cotações) não foi encontrado, faz uma segunda
    passagem com o padrão relaxado "X.Y. Texto..." para itens cujos pontos
    estão dispersos no corpo em vez de no cabeçalho.
    """
    matches = list(_ITEM_HEADER_RE.finditer(text))
    blocks: list[_CCBlock] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append(_CCBlock(
            id_item=m.group(1),
            cotacao=int(m.group(2)),
            text=text[m.end():end].strip(),
            offset=m.start(),
        ))

    found_ids = {b.id_item for b in blocks}

    # Itens implícitos com linha solta "15 pontos" sem id explícito.
    implicit_matches = list(_IMPLICIT_POINTS_HEADER_RE.finditer(text))
    for i, m in enumerate(implicit_matches):
        prev_explicit = next((x for x in reversed(matches) if x.start() < m.start()), None)
        next_explicit = next((x for x in matches if x.start() > m.start()), None)

        inferred_id: str | None = None
        if prev_explicit is None and next_explicit is not None:
            next_main = int(next_explicit.group(1).split(".")[0])
            if next_main > 1:
                inferred_id = str(next_main - 1)
        elif prev_explicit is not None and next_explicit is not None:
            prev_main = int(prev_explicit.group(1).split(".")[0])
            next_main = int(next_explicit.group(1).split(".")[0])
            if next_main - prev_main >= 2:
                inferred_id = str(prev_main + 1)

        if not inferred_id or inferred_id in found_ids:
            continue

        end_candidates = [x.start() for x in matches if x.start() > m.start()]
        next_implicit = next((x.start() for x in implicit_matches[i + 1:] if x.start() > m.start()), None)
        if next_implicit is not None:
            end_candidates.append(next_implicit)
        end = min(end_candidates) if end_candidates else len(text)
        block_text = text[m.end():end].strip()
        if not block_text:
            continue

        blocks.append(_CCBlock(
            id_item=inferred_id,
            cotacao=int(m.group(1)),
            text=block_text,
            offset=m.start(),
        ))
        found_ids.add(inferred_id)
        print(f"[cc_extract] 🔍 {inferred_id} detetado via cabeçalho implícito '{m.group(0).strip()}'")

    # Segunda passagem: itens esperados com cabeçalho "X.Y. Texto" (pontos no corpo)
    if expected_cotacoes:
        # Normalizar: IDs esperados sem prefixo de grupo ("II-3.1" → "3.1")
        missing_plain = {
            re.sub(r"^[IVX]+-", "", eid): (eid, pts)
            for eid, pts in expected_cotacoes.items()
            if re.sub(r"^[IVX]+-", "", eid) not in found_ids and eid not in found_ids
        }
        if missing_plain:
            inline_matches = list(_ITEM_HEADER_INLINE_RE.finditer(text))
            for i, m in enumerate(inline_matches):
                plain_id = m.group(1)
                if plain_id in missing_plain:
                    orig_id, cotacao = missing_plain[plain_id]
                    end = inline_matches[i + 1].start() if i + 1 < len(inline_matches) else len(text)
                    # Verificar que este bloco não sobrepõe um bloco já existente
                    overlap = any(
                        m.start() >= text.find(b.text) and m.start() <= text.find(b.text) + len(b.text)
                        for b in blocks if b.text
                    )
                    if not overlap:
                        blocks.append(_CCBlock(
                            id_item=plain_id,
                            cotacao=cotacao,
                            text=text[m.start():end].strip(),
                            offset=m.start(),
                        ))
                        print(f"[cc_extract] 🔍 {plain_id} detetado via cabeçalho inline (pontos no corpo)")

    return blocks



def _load_tipo_por_id(questoes_review_path: Path | None) -> dict[str, str]:
    """Lê questoes_review.json (workspace principal) e devolve {id_item: tipo_item}.

    As chaves são os `id_item` originais (com prefixo de grupo, ex.: "I-6", "II-3.1").
    O caller é responsável por reconstruir o ID completo a partir do grupo do bloco
    no markdown CC (que contém apenas IDs planos como "6" ou "3.1").
    """
    if not questoes_review_path or not questoes_review_path.exists():
        return {}
    try:
        items = json.loads(questoes_review_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for it in items:
        tid = (it.get("id_item") or "").strip()
        tip = (it.get("tipo_item") or "").strip()
        if tid and tip:
            out[tid] = tip
    return out


def _build_group_index(text: str) -> list[tuple[int, str]]:
    """Devolve [(offset, grupo)] ordenados — offset onde cada GRUPO X começa.

    Permite localizar em que grupo cada bloco do markdown CC se insere,
    procurando o último heading `# GRUPO X` antes do offset do bloco.
    """
    return [
        (m.start(), m.group(1).upper())
        for m in _GROUP_HEADING_RE.finditer(text)
    ]


def _grupo_em_offset(group_index: list[tuple[int, str]], offset: int) -> str:
    """Encontra o último GRUPO X cujo offset precede `offset`. '' se nenhum."""
    grupo = ""
    for off, g in group_index:
        if off <= offset:
            grupo = g
        else:
            break
    return grupo


def _parse_multi_select_answers(text: str) -> list[str]:
    """Extrai uma lista de algarismos romanos (I–V) de um bloco curto de CC.

    Heurística conservadora: só devolve lista se encontrar pelo menos 2 ocorrências
    e se o bloco for curto (típico de respostas de multi_select). Devolução vazia
    sinaliza que o agente tem de extrair manualmente do PDF.
    """
    # Limitar a primeiras 3 linhas não vazias — respostas costumam estar no topo
    head = "\n".join([l for l in text.splitlines() if l.strip()][:3])
    candidatos = _MULTI_SELECT_ROMAN_RE.findall(head)
    # Filtrar duplicados preservando ordem
    seen: set[str] = set()
    unicos: list[str] = []
    for c in candidatos:
        if c not in seen:
            seen.add(c)
            unicos.append(c)
    return unicos if len(unicos) >= 2 else []


def extract_cc(
    settings: Settings,
    markdown_path: Path,
    fonte: str = "",
    questoes_review_path: Path | None = None,
) -> Path:
    """
    Lê o markdown gerado pelo MinerU para um CC-VD e extrai critérios estruturados.

    Entrada : prova.md (gerado por `exames_pipeline extract <cc_pdf> --no-preprocess`)
    Saída   : criterios_raw.json no mesmo directório

    Se `questoes_review_path` for fornecido, o tipo de cada questão é cruzado
    com o critério: tipos `multi_select`, `complete_table` e `essay` nunca são
    classificados como `multiple_choice`, evitando contaminação por OCR (ex:
    `Opção (B)` capturado erradamente para um item multi_select).
    """
    markdown_path = markdown_path.resolve()
    output_dir = markdown_path.parent
    resolved_fonte = fonte or infer_fonte_from_path(markdown_path)
    is_pt = "portugu" in resolved_fonte.lower() or "portugu" in str(markdown_path).lower()
    tipo_por_id = _load_tipo_por_id(questoes_review_path)

    markdown = markdown_path.read_text(encoding="utf-8")
    text = _find_criterios_especificos(markdown)

    # Carregar cotações esperadas antes de segmentar (usadas na 2.ª passagem)
    cotacoes_path = output_dir / "cotacoes_estrutura.json"
    expected_cotacoes: dict[str, int] = {}
    if cotacoes_path.exists():
        try:
            cotacoes_data = json.loads(cotacoes_path.read_text(encoding="utf-8"))
            expected_cotacoes = cotacoes_data.get("cotacoes", {})
        except Exception:
            pass

    blocks = _segment_blocks(text, expected_cotacoes=expected_cotacoes)
    group_index = _build_group_index(text)

    if not blocks:
        print("[cc_extract] ⚠️  Nenhum cabeçalho de item encontrado. "
              "Verifica se o markdown contém 'CRITÉRIOS ESPECÍFICOS DE CLASSIFICAÇÃO'.")

    criterios: list[CriterioRaw] = []
    traces: list[dict] = []
    mc_preamble_map = _extract_mc_preamble_map(markdown)

    for block in blocks:
        block.text, auto_fixes = _auto_correct(block.text, is_pt=is_pt)
        imagens = _IMAGE_REF_RE.findall(block.text)

        # Cruzamento com o tipo_item da questão (workspace principal)
        # O markdown CC usa IDs planos ("6"); compor o ID completo via grupo ("I-6").
        grupo_atual = _grupo_em_offset(group_index, block.offset)
        id_completo = f"{grupo_atual}-{block.id_item}" if grupo_atual else block.id_item
        tipo_questao = tipo_por_id.get(id_completo) or tipo_por_id.get(block.id_item)
        # Em PT, prefixar o id_item do critério com o grupo elimina colisões
        # entre I-6 e II-6 (ambos com id plano "6" no markdown CC).
        if is_pt and grupo_atual:
            block.id_item = id_completo
        # Tipos não-MC: nunca aceitar "Opção (X)" como resposta
        tipo_forca_nao_mc = tipo_questao in {"multi_select", "complete_table", "essay"}

        # Caso 1: "Opção (X)" explícito
        mc_match = None if tipo_forca_nao_mc else _MC_ANSWER_RE.search(block.text)
        # Caso 2: "(X)" isolado numa linha (sem prefixo "Opção")
        if not mc_match and not tipo_forca_nao_mc:
            mc_match = _MC_BARE_ANSWER_RE.search(block.text)
        mc_letter = (
            mc_match.group(1).upper() if mc_match
            else (None if tipo_forca_nao_mc else mc_preamble_map.get(block.id_item))
        )

        # Ramo dedicado para multi_select / complete_table / essay
        if tipo_forca_nao_mc:
            obs = [
                f"Tipo da questão é '{tipo_questao}': resposta requer extração manual do PDF CC-VD."
            ]
            obs += [f"[auto-fix] {f}" for f in auto_fixes]
            respostas: list[str] = []
            criterios_parciais: list[dict] = []
            if tipo_questao == "multi_select":
                respostas = _parse_multi_select_answers(block.text)
                if respostas:
                    obs.append(
                        f"Respostas multi_select extraídas heuristicamente: {respostas} — confirmar contra o PDF."
                    )
            elif tipo_questao == "essay":
                # tentar extrair níveis de desempenho (mesmo caminho do open_response PT)
                if _NIVEL_DESEMPENHO_RE.search(block.text):
                    niveis = _parse_niveis_desempenho(block.text)
                    criterios_parciais = [
                        {"nivel": n["nivel"], "pontos": n["pontos"], "descricao": n["descritor"]}
                        for n in niveis
                    ]
            criterio = CriterioRaw(
                id_item=block.id_item,
                cotacao_total=block.cotacao,
                tipo=tipo_questao,
                resposta_correta=None,
                solucao=block.text,
                criterios_parciais=criterios_parciais,
                resolucoes_alternativas=[],
                status="pending_review",
                texto_original=block.text,
                fonte=resolved_fonte,
                imagens=imagens,
                contexto="",
                observacoes=obs,
                respostas_corretas=respostas,
            )
            print(f"[cc_extract] ⚠️  {block.id_item} ({tipo_questao}) → pending_review (resposta requer PDF CC-VD)")
            criterios.append(criterio)
            traces.append(
                {
                    "id_item": criterio.id_item,
                    "cotacao_total": criterio.cotacao_total,
                    "tipo_inferido": criterio.tipo,
                    "status_inicial": criterio.status,
                    "ocr_tem_opcao_inline": False,
                    "ocr_tem_resposta_mc": False,
                    "n_criterios_parciais": len(criterio.criterios_parciais),
                    "n_resolucoes_alternativas": 0,
                    "n_respostas_corretas": len(criterio.respostas_corretas),
                    "criterio": criterio.to_dict(),
                }
            )
            continue

        if mc_letter:
            obs = [] if mc_match else ["Resposta MC extraída do preâmbulo (não estava inline)"]
            obs += [f"[auto-fix] {f}" for f in auto_fixes]
            criterio = CriterioRaw(
                id_item=block.id_item,
                cotacao_total=block.cotacao,
                tipo="multiple_choice",
                resposta_correta=mc_letter,
                solucao="",
                criterios_parciais=[],
                resolucoes_alternativas=[],
                status="draft",
                texto_original=block.text,
                fonte=resolved_fonte,
                imagens=imagens,
                contexto="",
                observacoes=obs,
            )
            icon = "⚠️" if obs else "✅"
            print(f"[cc_extract] {icon} {block.id_item} (EM) → {mc_letter}{' [preâmbulo]' if obs else ''}")
        else:
            # PT: tentar detetar níveis de desempenho primeiro
            if is_pt and _NIVEL_DESEMPENHO_RE.search(block.text):
                niveis = _parse_niveis_desempenho(block.text)
                criterios_parciais = (
                    [{"nivel": n["nivel"], "pontos": n["pontos"], "descricao": n["descritor"]}
                     for n in niveis]
                    if niveis else []
                )
                resolucoes_alternativas = []
                contexto = ""
            else:
                criterios_parciais, resolucoes_alternativas, contexto = _parse_open_criteria(block.text)
            status = "draft" if criterios_parciais else "pending_review"
            observacoes = []
            if status == "pending_review":
                observacoes.append("Extractor não conseguiu segmentar etapas com confiança suficiente.")
            observacoes += [f"[auto-fix] {f}" for f in auto_fixes]
            criterio = CriterioRaw(
                id_item=block.id_item,
                cotacao_total=block.cotacao,
                tipo="open_response",
                resposta_correta=None,
                solucao=block.text,
                criterios_parciais=criterios_parciais,
                resolucoes_alternativas=resolucoes_alternativas,
                status=status,
                texto_original=block.text,
                fonte=resolved_fonte,
                imagens=imagens,
                contexto=contexto,
                observacoes=observacoes,
            )
            icon = "⚠️" if status == "pending_review" else "✅"
            n_steps = len(criterio.criterios_parciais)
            print(f"[cc_extract] {icon} {block.id_item} (RD) → {n_steps} etapas")

        criterios.append(criterio)
        traces.append(
            {
                "id_item": criterio.id_item,
                "cotacao_total": criterio.cotacao_total,
                "tipo_inferido": criterio.tipo,
                "status_inicial": criterio.status,
                "ocr_tem_opcao_inline": bool(mc_match),
                "ocr_tem_resposta_mc": bool(mc_letter),
                "n_criterios_parciais": len(criterio.criterios_parciais),
                "n_resolucoes_alternativas": len(criterio.resolucoes_alternativas),
                "criterio": criterio.to_dict(),
            }
        )

    # Post-pass: adicionar itens esperados que não foram encontrados no markdown.
    # Evitar duplicados quando cotacoes usa prefixos de grupo ("II-2.1") mas o
    # markdown usa IDs simples ("2.1"): o found_id "2.1" já cobre "II-2.1".
    if expected_cotacoes:
        found_ids = {c.id_item for c in criterios}

        def _is_covered(expected_id: str) -> bool:
            """True se o ID esperado já está coberto por um found_id (com ou sem prefixo de grupo)."""
            if expected_id in found_ids:
                return True
            # "II-2.1" → plain "2.1"
            plain = re.sub(r"^[IVX]+-", "", expected_id)
            return plain in found_ids

        for item_id, cotacao in expected_cotacoes.items():
            if not _is_covered(item_id):
                print(f"[cc_extract] ⚠️  {item_id} → ausente do markdown (pending_review)")
                criterios.append(CriterioRaw(
                    id_item=item_id,
                    cotacao_total=cotacao,
                    tipo="open_response",
                    resposta_correta=None,
                    solucao="",
                    criterios_parciais=[],
                    resolucoes_alternativas=[],
                    status="pending_review",
                    texto_original="",
                    fonte=resolved_fonte,
                    imagens=[],
                    contexto="",
                    observacoes=[
                        "Item ausente do markdown — requer revisão do agente contra o PDF original.",
                    ],
                ))
                traces.append(
                    {
                        "id_item": item_id,
                        "cotacao_total": cotacao,
                        "tipo_inferido": "open_response",
                        "status_inicial": "pending_review",
                        "ocr_tem_opcao_inline": False,
                        "ocr_tem_resposta_mc": False,
                        "n_criterios_parciais": 0,
                        "n_resolucoes_alternativas": 0,
                        "criterio": criterios[-1].to_dict(),
                    }
                )

    output_path = output_dir / "criterios_raw.json"
    traces_path = output_dir / "criterios_raw.traces.json"
    dump_criterios(output_path, criterios)
    dump_json(traces_path, traces)
    print(f"\n[cc_extract] {len(criterios)} itens → {output_path}")

    # Lint OCR — adiciona OCR-SUSPECT às observações e gera criterios_ocr_flags.json
    print("")
    _, n_flagged = lint_criterios(output_path)

    # Re-ler após lint (lint pode ter modificado as observações) para gerar view compacta
    from .schemas import load_criterios  # noqa: PLC0415
    criterios_after_lint = load_criterios(output_path)
    review_path = _dump_review_json(output_dir, criterios_after_lint)
    print(f"[cc_extract] 📋 criterios_review.json → {review_path.name}")
    if n_flagged:
        print(f"[cc_extract] ⚠️  criterios_ocr_flags.json — {n_flagged} item(ns) requerem atenção")

    return output_path
