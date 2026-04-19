from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess


# Detetar cabeçalhos de grupo: "# Grupo I", "## GRUPO II", "# \* GRUPO III", etc.
# O \* antes de GRUPO é artefacto OCR do MinerU em alguns PDFs.
_GRUPO_HEADING_RE = re.compile(
    r"(?m)^#{1,3}\s*(?:\\\*\s*)?[Gg][Rr][Uu][Pp][Oo]\s+(?P<num>I{1,3}|IV|VI{0,3}|IX|X)\b"
)
# Detetar cabeçalhos de parte: "# PARTE A", "# Parte B", etc.
_PARTE_HEADING_RE = re.compile(
    r"(?m)^#{1,3}\s+[Pp][Aa][Rr][Tt][Ee]\s+[A-Z]\b"
)
# Mapa de numeral romano → string canónica
_ROMANO_CANON = {"I": "I", "II": "II", "III": "III", "IV": "IV", "V": "V",
                 "VI": "VI", "VII": "VII", "VIII": "VIII", "IX": "IX", "X": "X"}

IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
QUESTION_HEADING_PATTERN = re.compile(
    r"(?m)^(?:\$\\(?:star|bigstar|ast)\$\s*|\$?\\pm\s*|\\[*]\s*|[\*\u00b1•-]\s*)?(?:Quest[aã]o\s+)?(?P<label>\d{1,3}(?:\.\d{1,2})?)(?:\s*\.\s*\$?\s+|(?=[A-ZÁÉÍÓÚÀÂÃÇ]))"
)
# Padrão para provas com numeração prefixada por grupo romano: "I-1. Enunciado"
_ROMAN_PREFIX_QUESTION_RE = re.compile(
    r"(?m)^(?:I{1,3}|IV|VI{0,3}|IX|X)-(?P<label>\d{1,3}(?:\.\d{1,2})?)\.?\s+(?=[A-ZÁÉÍÓÚÀÂÃÇO])"
)
INLINE_SUBHEADING_PATTERN = re.compile(
    r"(?P<prefix>\s|[\*\u2605])(?P<label>\d{1,3}\.\d{1,2})\.\s+"
)
POST_CHOICE_BOUNDARY_PATTERN = re.compile(
    r"(?P<prefix>\s+[\*•-]?\s*)(?P<marker>(?:O|Uma|Um|Seja|Considere|Na Figura|A Figura|Admita que|Para certos valores|Para um certo número real)[^\n]{10,})",
    re.IGNORECASE,
)
ALTERNATIVE_PATTERN = re.compile(r"\(([A-D])\)\s*(.*?)(?=(?:\s+\([A-D]\)\s*)|$)", re.DOTALL)
MULTIPLE_CHOICE_STEM_PATTERN = re.compile(
    r"\b(qual das|em qual das|qual dos|qual das express[oõ]es seguintes|qual das equa[cç][oõ]es seguintes)\b",
    re.IGNORECASE,
)
VISUAL_REFERENCE_PATTERN = re.compile(
    r"\b(figura|gr[aá]fico|imagem|esquema|circunfer[êe]ncia|prisma|tri[âa]ngulo|plano complexo)\b",
    re.IGNORECASE,
)
COMPLETION_PATTERN = re.compile(r"\bcomplete o texto\b", re.IGNORECASE)
IMPLICIT_BOUNDARY_PATTERN = re.compile(
    r"(?m)^(?P<marker>"
    r"O gr[aá]fico da Figura\s+\d+.*|"
    r"Complete o texto seguinte,.*|"
    r"Para certos valores reais.*|"
    r"Na Figura\s+\d+, est[aá] representad[oa].*"
    r")$"
)
SENTENCE_START_NEW_ITEM_PATTERN = re.compile(
    r"^(?:O gr[aá]fico|Na Figura|Considere|Admita que|Para certos valores|Seja |Em \$?\\mathbb|Resolva|Mostre que|Determine|Complete o texto)",
    re.IGNORECASE,
)
CONTINUATION_PATTERN = re.compile(
    r"^(?:Apresente|Justifique|Escreva|Selecione|indique|represente|assinale|não justifique|na sua resposta)",
    re.IGNORECASE,
)
VISUAL_OPENING_PATTERN = re.compile(r"^(?:O gr[aá]fico|Na Figura|Admita que)", re.IGNORECASE)


@dataclass(slots=True)
class MarkdownQuestionBlock:
    ordem_item: int
    item_id: str
    numero_principal: int
    subitem: str | None
    heading_label_raw: str
    raw_markdown: str
    imagens: list[str]
    imagens_contexto: list[str]
    source_span: dict[str, int]
    suspected_numbering_reset: bool = False
    inferred_from_implicit_boundary: bool = False
    implicit_boundary_score: int | None = None
    implicit_boundary_reasons: list[str] | None = None
    inferred_type: str = "unknown"
    grupo: str = ""          # "I", "II", … — vazio quando a prova não tem grupos
    is_context_stem: bool = False
    section_context: str = ""  # texto da secção (PARTE A/B/C, GRUPO II) que precede as questões


_MATERIA_CODES: dict[str, str] = {
    "MatA": "Matemática A",
    "MatB": "Matemática B",
    "Port": "Português",
    "FQ":   "Física e Química",
    "Bio":  "Biologia e Geologia",
    "Hist": "História",
    "Geo":  "Geografia",
    "EF":   "Educação Física",
    "Filo": "Filosofia",
    "Ing":  "Inglês",
    "Fran": "Francês",
    "Esp":  "Espanhol",
}

_FASE_CODES: dict[str, str] = {
    "F1": "1.ª Fase",
    "F2": "2.ª Fase",
    "FE": "Fase Especial",
    "FR": "Recurso",
}

# EX-MatA635-F1-2024_net  ou  EX-MatA635-F1-2024-CC-VD
_FONTE_PATTERN = re.compile(
    r"EX-(?P<materia>[A-Za-z]+)\d*-(?P<fase>F\w+)-(?P<ano>\d{4})",
    re.IGNORECASE,
)


def infer_fonte_from_path(path: Path) -> str:
    """Infere a descrição legível da prova a partir do nome do ficheiro ou do diretório pai.

    Procura o padrão EX-* no nome do ficheiro e, se não encontrar (ex: ficheiros
    normalizados como 'prova.md'), sobe para o diretório pai (ex: EX-MatA635-F1-2024_net/).

    Exemplos:
      EX-MatA635-F1-2024_net.pdf         →  "Exame Nacional, Matemática A, 1.ª Fase, 2024"
      workspace/EX-MatA635-F1-2021_net/prova.md  →  "Exame Nacional, Matemática A, 1.ª Fase, 2021"

    Devolve "" se o padrão não for reconhecido em nenhum nível.
    """
    # Tenta no nome do ficheiro primeiro, depois nos diretórios pais
    candidates = [path.stem] + [p.name for p in path.parents]
    for candidate in candidates:
        match = _FONTE_PATTERN.search(candidate)
        if match:
            materia_code = match.group("materia")
            fase_code = match.group("fase").upper()
            ano = match.group("ano")
            materia = _MATERIA_CODES.get(materia_code, materia_code)
            fase = _FASE_CODES.get(fase_code, fase_code)
            return f"Exame Nacional, {materia}, {fase}, {ano}"
    return ""


def slugify(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    sanitized = sanitized.strip("-")
    return sanitized or "documento"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_command(command: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        shell=True,
        check=False,
        capture_output=True,
        text=True,
    )


def extract_image_paths(markdown_block: str) -> list[str]:
    return IMAGE_PATTERN.findall(markdown_block)


def extract_alternatives(markdown_block: str) -> list[tuple[str, str]]:
    alternatives: list[tuple[str, str]] = []
    for letter, text in ALTERNATIVE_PATTERN.findall(markdown_block):
        normalized = _clean_inferred_alternative_text(text)
        alternatives.append((letter, normalized))
    return alternatives


def _clean_inferred_alternative_text(text: str) -> str:
    normalized = " ".join(text.split())
    normalized = re.sub(r"\s*\\\s*$", "", normalized).strip()
    normalized = re.sub(r"^\{\s*", "", normalized)
    normalized = re.sub(r"\s*\}$", "", normalized)
    normalized = re.sub(r"\\mathbb\{\s*R\s*\}\s*\}\s*$", r"\\mathbb{ R }", normalized)
    normalized = re.sub(r"\\mathbb\{\s*R\s*$", r"\\mathbb{ R }", normalized)
    normalized = re.sub(r"\\mathbb\{\s*R$", r"\\mathbb{ R }", normalized)
    normalized = re.sub(r"\\mathbb\s*\{\s*R\s*$", r"\\mathbb{ R }", normalized)
    normalized = re.sub(r"\\in\s+\\mathbb\{\s*R\s*$", r"\\in \\mathbb{ R }", normalized)
    normalized = re.sub(r"\\in\s+\\mathbb\s*\{\s*R\s*$", r"\\in \\mathbb{ R }", normalized)
    normalized = re.sub(r"\\in\s+\\mathbb\{\s*R\s*\}\s*\}\s*$", r"\\in \\mathbb{ R }", normalized)
    normalized = re.sub(r"\s+\{$", "", normalized)
    if normalized.endswith(r"\mathbb{ R"):
        normalized = normalized + " }"
    if normalized.endswith(r"\in \mathbb{ R"):
        normalized = normalized + " }"
    if not normalized.endswith(r"\mathbb{ R }") and not normalized.endswith(r"\in \mathbb{ R }"):
        normalized = re.sub(r"\s+\}\s*$", "", normalized)
    return normalized.strip()


def extract_latex_array_alternatives(markdown_block: str) -> list[tuple[str, str]]:
    alternatives: list[tuple[str, str]] = []
    math_blocks = re.findall(r"\$\$(.*?)\$\$", markdown_block, re.DOTALL)
    for math_block in math_blocks:
        if r"\begin{array}" not in math_block:
            continue
        body = re.sub(r"\\begin\{array\}(?:\s*\{[^{}]*\})+", "", math_block, count=1)
        body = re.sub(r"\\end\{array\}", "", body)
        rows = []
        for raw_row in body.split(r"\\"):
            cleaned = raw_row.replace("&", " ")
            cleaned = re.sub(r"\{\s*\}", " ", cleaned)
            cleaned = cleaned.strip(" {}")
            cleaned = _clean_inferred_alternative_text(cleaned)
            if not cleaned:
                continue
            if len(re.findall(r"[A-Za-z0-9]", cleaned)) < 6:
                continue
            rows.append(cleaned)
        if len(rows) == 4:
            return list(zip(["A", "B", "C", "D"], rows, strict=False))
    return alternatives


def extract_inferred_alternatives(markdown_block: str) -> list[tuple[str, str]]:
    explicit = extract_alternatives(markdown_block)
    if explicit:
        return explicit
    if MULTIPLE_CHOICE_STEM_PATTERN.search(markdown_block):
        return extract_latex_array_alternatives(markdown_block)
    return []


def infer_question_type(markdown_block: str) -> str:
    if len(extract_inferred_alternatives(markdown_block)) == 4:
        return "multiple_choice"
    if COMPLETION_PATTERN.search(markdown_block):
        return "completion"
    return "open_response"


def block_requires_multimodal(markdown_block: str, context_images: list[str] | None = None) -> bool:
    image_paths = extract_image_paths(markdown_block)
    nearby = context_images or []
    if image_paths or nearby:
        return True
    return bool(VISUAL_REFERENCE_PATTERN.search(markdown_block))


def _line_number_at(markdown_text: str, offset: int) -> int:
    return markdown_text.count("\n", 0, offset) + 1


def _normalize_heading_sequence(labels: list[str]) -> list[tuple[str, int, str | None, bool]]:
    normalized: list[tuple[str, int, str | None, bool]] = []
    previous_main_number: int | None = None

    for label in labels:
        parts = label.split(".")
        if len(parts) == 1:
            raw_main = int(parts[0])
            suspected_reset = False
            canonical_main = raw_main
            if previous_main_number is not None and raw_main <= previous_main_number:
                canonical_main = previous_main_number + 1
                suspected_reset = True
            previous_main_number = canonical_main
            normalized.append((str(canonical_main), canonical_main, None, suspected_reset))
            continue

        raw_parent = int(parts[0])
        raw_child = parts[1]
        # Atualiza o número principal se o pai declarado for maior (novo grupo legítimo)
        # Só marca suspected_reset quando o número volta atrás (artefacto OCR)
        if previous_main_number is None or raw_parent > previous_main_number:
            previous_main_number = raw_parent
        canonical_main = previous_main_number
        suspected_reset = raw_parent != canonical_main
        normalized.append((f"{canonical_main}.{raw_child}", canonical_main, raw_child, suspected_reset))
    return normalized


def _context_images(
    markdown_text: str,
    block_start: int,
    block_end: int,
    block_images: list[str],
    window: int = 400,
) -> list[str]:
    before = markdown_text[max(0, block_start - window):block_start]
    after = markdown_text[block_end:min(len(markdown_text), block_end + window)]
    nearby = extract_image_paths(before) + extract_image_paths(after)
    merged: list[str] = []
    for image in block_images + nearby:
        if image not in merged:
            merged.append(image)
    return merged


def _find_implicit_split_offsets(raw_block: str) -> list[tuple[int, int, list[str]]]:
    splits: list[tuple[int, int, list[str]]] = []
    for match in IMPLICIT_BOUNDARY_PATTERN.finditer(raw_block):
        offset = match.start()
        if offset <= 0:
            continue
        prefix = raw_block[:offset].rstrip()
        if not prefix.endswith((".", "?", "!", "$$", "]", ")")):
            continue
        splits.append((offset, 4, [f"padrao explicito: {match.group('marker')[:80]}"]))
    return splits


def _find_inline_subheading_offsets(raw_block: str, current_main_number: int) -> list[tuple[int, str]]:
    offsets: list[tuple[int, str]] = []
    for match in INLINE_SUBHEADING_PATTERN.finditer(raw_block):
        label = match.group("label")
        if not label.startswith(f"{current_main_number}."):
            continue
        offset = match.start("label")
        if offset <= 0:
            continue
        following = raw_block[match.end():match.end() + 40].lstrip()
        if not re.match(r"(?:Averigue|Estude|Determine|Mostre|Resolva|Calcule|Justifique|Apresente)\b", following):
            continue
        offsets.append((offset, label))
    return offsets


def _find_post_choice_split_offsets(raw_block: str) -> list[tuple[int, int, list[str]]]:
    d_matches = list(re.finditer(r"\(D\)", raw_block))
    if not d_matches:
        return []
    splits: list[tuple[int, int, list[str]]] = []
    for match_d in d_matches:
        tail = raw_block[match_d.end():]
        has_imperative = bool(
            re.search(r"\b(Escreva|Determine|Mostre|Resolva|Calcule|Averigue)\b", tail, re.IGNORECASE)
        )
        for marker in POST_CHOICE_BOUNDARY_PATTERN.finditer(tail):
            marker_text = marker.group("marker")
            marker_lower = marker_text.lower()
            offset = match_d.end() + marker.start("marker")
            score = 5 if has_imperative else 4
            reasons = [f"cauda apos alternativa D parece novo enunciado: {marker_text[:80]}"]

            if marker_lower.startswith("um desporto coletivo"):
                previous_sentence = re.search(
                    r"(?P<start>\*?O\s+[^\n]{5,}?)(?=\s+Um desporto coletivo)",
                    tail,
                    re.IGNORECASE,
                )
                if previous_sentence:
                    offset = match_d.end() + previous_sentence.start("start")
                    marker_text = previous_sentence.group("start")
                    reasons = [f"cauda apos alternativa D parece novo enunciado: {marker_text[:80]}"]

            if not has_imperative:
                reasons.append("sem verbo imperativo, mas marcador discursivo forte apos bloco MC")

            splits.append((offset, score, reasons))

    return splits


def _paragraphs_with_offsets(raw_block: str) -> list[tuple[int, str]]:
    paragraphs: list[tuple[int, str]] = []
    for match in re.finditer(r"(?s)(?:^|\n\n)(.*?)(?=\n\n|$)", raw_block):
        text = match.group(1).strip()
        if not text:
            continue
        offset = match.start(1)
        paragraphs.append((offset, text))
    return paragraphs


def _last_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _first_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[0] if lines else ""


def _discursive_boundary_score(previous_text: str, candidate_text: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    prev_last = _last_nonempty_line(previous_text)
    cand_first = _first_nonempty_line(candidate_text)
    prev_lower = previous_text.lower()
    cand_lower = candidate_text.lower()

    if SENTENCE_START_NEW_ITEM_PATTERN.search(cand_first):
        score += 2
        reasons.append("inicio tipico de novo enunciado")
    if VISUAL_OPENING_PATTERN.search(cand_first):
        score += 2
        reasons.append("abertura visual tipica")
    if "figura" in cand_lower or "gráfico" in cand_lower or "grafico" in cand_lower:
        score += 1
        reasons.append("referencia visual")
    if COMPLETION_PATTERN.search(candidate_text):
        score += 2
        reasons.append("padrao de completamento")
    if candidate_text.startswith("![]("):
        score -= 2
        reasons.append("bloco começa por imagem, parece contexto")
    if CONTINUATION_PATTERN.search(cand_first):
        score -= 2
        reasons.append("inicio tipico de continuacao")
    if prev_last.endswith(":"):
        score -= 2
        reasons.append("trecho anterior termina em dois pontos")
    if prev_last.endswith(";"):
        score -= 1
        reasons.append("trecho anterior termina em ponto e virgula")
    if prev_last.startswith("Sabe-se que"):
        score -= 1
        reasons.append("trecho anterior ainda introduz condicoes")
    if prev_last and not re.search(r"[.!?]$", prev_last):
        score -= 1
        reasons.append("trecho anterior sem fecho forte")
    if extract_image_paths(candidate_text) and not extract_image_paths(previous_text):
        score += 1
        reasons.append("entra novo contexto de imagem")
    if ("determine o valor de" in prev_lower or "mostre que" in prev_lower) and (
        "o gráfico da figura" in cand_lower or "para certos valores reais" in cand_lower
    ):
        score += 3
        reasons.append("mudanca brusca de tarefa")

    return score, reasons


def _infer_discursive_split_offsets(raw_block: str) -> list[tuple[int, int, list[str]]]:
    paragraphs = _paragraphs_with_offsets(raw_block)
    splits: list[tuple[int, int, list[str]]] = []
    if len(paragraphs) < 2:
        return splits

    accumulated = paragraphs[0][1]
    for offset, paragraph in paragraphs[1:]:
        score, reasons = _discursive_boundary_score(accumulated, paragraph)
        if score >= 3:
            splits.append((offset, score, reasons))
            accumulated = paragraph
        else:
            accumulated = f"{accumulated}\n\n{paragraph}"
    return splits


def _build_block(
    markdown_text: str,
    start: int,
    end: int,
    item_id: str,
    main_number: int,
    subitem: str | None,
    heading_label_raw: str,
    suspected_reset: bool,
    inferred_from_implicit_boundary: bool,
    implicit_boundary_score: int | None = None,
    implicit_boundary_reasons: list[str] | None = None,
) -> MarkdownQuestionBlock | None:
    raw_block = markdown_text[start:end].strip()
    if not raw_block:
        return None
    raw_block = re.sub(r"^\*+(?=[A-ZÁÉÍÓÚÀÂÃÇO])", "", raw_block).strip()
    raw_block = re.sub(r"\s*\\\s*$", "", raw_block).strip()
    line_start = _line_number_at(markdown_text, start)
    line_end = _line_number_at(markdown_text, end)
    block_images = extract_image_paths(raw_block)
    return MarkdownQuestionBlock(
        ordem_item=0,
        item_id=item_id,
        numero_principal=main_number,
        subitem=subitem,
        heading_label_raw=heading_label_raw,
        raw_markdown=raw_block,
        imagens=block_images,
        imagens_contexto=_context_images(markdown_text, start, end, block_images),
        source_span={"line_start": line_start, "line_end": line_end},
        suspected_numbering_reset=suspected_reset,
        inferred_from_implicit_boundary=inferred_from_implicit_boundary,
        implicit_boundary_score=implicit_boundary_score,
        implicit_boundary_reasons=implicit_boundary_reasons,
        inferred_type=infer_question_type(raw_block),
    )


def _expand_implicit_boundaries(
    markdown_text: str,
    block_specs: list[tuple[int, int, str, int, str | None, str, bool]],
) -> list[MarkdownQuestionBlock]:
    expanded: list[MarkdownQuestionBlock] = []

    for index, (start, end, item_id, main_number, subitem, heading_label_raw, suspected_reset) in enumerate(block_specs):
        raw_block = markdown_text[start:end].strip()
        explicit_like_splits = _find_implicit_split_offsets(raw_block)
        post_choice_splits = _find_post_choice_split_offsets(raw_block)
        discursive_splits = _infer_discursive_split_offsets(raw_block)
        merged_split_map: dict[int, tuple[int, list[str]]] = {}
        for offset, score, reasons in explicit_like_splits + post_choice_splits + discursive_splits:
            previous = merged_split_map.get(offset)
            if previous is None or score > previous[0]:
                merged_split_map[offset] = (score, reasons)
        implicit_splits = sorted(
            [(offset, score, reasons) for offset, (score, reasons) in merged_split_map.items()],
            key=lambda item: item[0],
        )

        next_top_level: int | None = None
        for later in block_specs[index + 1:]:
            later_main = later[3]
            later_subitem = later[4]
            if later_subitem is None:
                next_top_level = later_main
                break

        available_new_items = None if next_top_level is None else max(0, next_top_level - main_number - 1)
        if available_new_items is not None:
            implicit_splits = implicit_splits[:available_new_items]

        should_infer_split = bool(implicit_splits)
        if not should_infer_split:
            block = _build_block(
                markdown_text,
                start,
                end,
                item_id,
                main_number,
                subitem,
                heading_label_raw,
                suspected_reset,
                False,
            )
            if block is not None:
                expanded.append(block)
            continue

        boundaries = [0, *[offset for offset, _, _ in implicit_splits], len(markdown_text[start:end])]
        inferred_main = main_number
        for piece_index in range(len(boundaries) - 1):
            piece_start = start + boundaries[piece_index]
            piece_end = start + boundaries[piece_index + 1]
            if piece_index == 0:
                piece_main = main_number
                piece_item_id = item_id
                piece_heading_raw = heading_label_raw
                piece_implicit = False
                piece_subitem = subitem
                piece_score = None
                piece_reasons = None
            else:
                inferred_main += 1
                if next_top_level is not None and inferred_main >= next_top_level:
                    break
                piece_main = inferred_main
                piece_item_id = str(piece_main)
                piece_heading_raw = f"implicit-{piece_item_id}"
                piece_implicit = True
                piece_subitem = None
                _, piece_score, piece_reasons = implicit_splits[piece_index - 1]
            block = _build_block(
                markdown_text,
                piece_start,
                piece_end,
                piece_item_id,
                piece_main,
                piece_subitem,
                piece_heading_raw,
                suspected_reset or piece_implicit,
                piece_implicit,
                piece_score,
                piece_reasons,
            )
            if block is not None:
                expanded.append(block)

    for order, block in enumerate(expanded, start=1):
        block.ordem_item = order
    return expanded


def _extract_post_choice_context(markdown_text: str, block_start: int, block_end: int) -> tuple[int, int, int]:
    """Extrai contexto de enunciado que ficou colado após as alternativas (D) de um bloco MCQ.

    Caso típico: bloco do item 2 tem enunciado + (A)(B)(C)(D) + "Um saco contém..."
    onde o texto após (D) é o enunciado/contexto do próximo grupo.

    Devolve (novo_block_end, ctx_start, ctx_end).
    Se não há contexto extra, devolve (block_end, block_end, block_end).
    """
    raw = markdown_text[block_start:block_end]
    alts_d = list(re.finditer(r"\(D\)[^\n]*", raw))
    if not alts_d:
        return block_end, block_end, block_end

    d_end_rel = alts_d[-1].end()
    tail_raw = raw[d_end_rel:]
    tail_stripped = tail_raw.strip()

    if not tail_stripped or tail_stripped.startswith(("$$", "#", "![", "(")):
        return block_end, block_end, block_end

    # Encontrar posição exacta do início do tail no texto original
    ctx_start = block_start + d_end_rel + (len(tail_raw) - len(tail_raw.lstrip("\n ")))
    ctx_end = block_end
    new_block_end = block_start + d_end_rel

    return new_block_end, ctx_start, ctx_end


def _last_context_paragraph(markdown_text: str, prev_end: int, next_start: int) -> tuple[int, int]:
    """Devolve (start, end) do último parágrafo de texto-enunciado entre prev_end e next_start.

    Ignora blocos LaTeX, headings Markdown, linhas de imagem e secções de formulário,
    que são ruído de cabeçalho/formulário da prova.
    """
    window = markdown_text[prev_end:next_start]
    # Percorre os parágrafos ao contrário para encontrar o último válido
    for match in reversed(list(re.finditer(r"(?m)^(.+(?:\n(?!\n).+)*)$", window))):
        text = match.group(1).strip()
        if not text:
            continue
        # Ignorar blocos LaTeX, headings Markdown, imagens e tabelas
        if text.startswith(("$$", "#", "![", "|")):
            continue
        # Ignorar linhas de formulário/cabeçalho da prova
        if re.match(
            r"^\s*(?:Geometria|Progressões|Trigonometria|Derivadas|Complexos|Limites notáveis"
            r"|Regras de derivação|12\.º Ano|Decreto-Lei|Duração da Prova|É permitido"
            r"|Não é permitido|Utilize apenas|Apresente apenas|As cotações|A prova inclui"
            r"|Para cada resposta|Nas respostas)",
            text,
            re.IGNORECASE,
        ):
            continue
        ctx_start = prev_end + match.start()
        ctx_end = prev_end + match.end()
        return ctx_start, ctx_end
    return next_start, next_start


def _inject_missing_parent_blocks(
    markdown_text: str,
    block_specs: list[tuple[int, int, str, int, str | None, str, bool]],
) -> list[tuple[int, int, str, int, str | None, str, bool]]:
    """Injeta blocos-pai sintéticos para grupos de subitens sem item principal explícito.

    Caso típico: a prova apresenta '1.1. Estude...' como primeiro heading, sem '1. ...',
    mas existe texto de contexto antes do subitem (ex: 'Considere a sucessão...').
    Quando esse texto existe, é injetado como bloco pai com subitem=None.
    """
    if not block_specs:
        return block_specs

    explicit_parents: set[int] = {
        main for _, _, _, main, sub, _, _ in block_specs if sub is None
    }

    result: list[tuple[int, int, str, int, str | None, str, bool]] = []
    for i, (start, end, item_id, main_number, subitem, heading_label_raw, suspected_reset) in enumerate(block_specs):
        if subitem is not None and main_number not in explicit_parents:
            ctx_start = ctx_end = start  # default: sem contexto

            # Estratégia 1: texto livre entre fim do bloco anterior e início deste subitem
            prev_end = block_specs[i - 1][1] if i > 0 else 0
            ctx_start, ctx_end = _last_context_paragraph(markdown_text, prev_end, start)

            # Estratégia 2: contexto colado após alternativas (D) do bloco anterior (MCQ)
            if ctx_start >= ctx_end and i > 0:
                prev_spec = block_specs[i - 1]
                new_prev_end, ctx_start, ctx_end = _extract_post_choice_context(
                    markdown_text, prev_spec[0], prev_spec[1]
                )
                if ctx_start < ctx_end and result and result[-1][0] == prev_spec[0]:
                    # Truncar o bloco anterior para remover o contexto que vai ser pai
                    result[-1] = (result[-1][0], new_prev_end) + result[-1][2:]

            if ctx_start < ctx_end:
                result.append((
                    ctx_start,
                    ctx_end,
                    str(main_number),
                    main_number,
                    None,
                    f"implicit-parent-{main_number}",
                    False,
                ))
            explicit_parents.add(main_number)
        result.append((start, end, item_id, main_number, subitem, heading_label_raw, suspected_reset))

    return result


def _expand_inline_subheadings(
    markdown_text: str,
    block_specs: list[tuple[int, int, str, int, str | None, str, bool]],
) -> list[tuple[int, int, str, int, str | None, str, bool]]:
    expanded: list[tuple[int, int, str, int, str | None, str, bool]] = []

    for start, end, item_id, main_number, subitem, heading_label_raw, suspected_reset in block_specs:
        raw_block = markdown_text[start:end]
        inline_offsets = _find_inline_subheading_offsets(raw_block, main_number)
        if not inline_offsets:
            expanded.append((start, end, item_id, main_number, subitem, heading_label_raw, suspected_reset))
            continue

        boundaries = [0, *[offset for offset, _ in inline_offsets], len(raw_block)]
        labels = [item_id, *[label for _, label in inline_offsets]]
        for index in range(len(boundaries) - 1):
            piece_start = start + boundaries[index]
            piece_end = start + boundaries[index + 1]
            label = labels[index]
            parts = label.split(".")
            piece_main = int(parts[0])
            piece_subitem = parts[1] if len(parts) > 1 else None
            expanded.append(
                (
                    piece_start,
                    piece_end,
                    label,
                    piece_main,
                    piece_subitem,
                    label,
                    suspected_reset,
                )
            )

    return expanded


def _mark_context_stems(blocks: list[MarkdownQuestionBlock]) -> list[MarkdownQuestionBlock]:
    """Marks parent blocks as context_stem when they have subitems in the block list.

    Example: if blocks include item "3", "3.1", "3.2", then item "3" is marked
    as context_stem because it only provides context for the subitems.
    """
    parents_with_subitems: set[int] = {
        block.numero_principal
        for block in blocks
        if block.subitem is not None
    }
    for block in blocks:
        if block.subitem is None and block.numero_principal in parents_with_subitems:
            block.is_context_stem = True
            block.inferred_type = "context_stem"
    return blocks


def _redistribute_images_by_reference(
    blocks: list[MarkdownQuestionBlock],
) -> list[MarkdownQuestionBlock]:
    """Move image tags to the block whose text references them.

    Rule: if a context_stem mentions 'Figura' but has no ![]() images,
    and the immediately following subitem(s) contain images, move those
    images to the context_stem — they belong to the shared context, not
    to individual subitems.
    """
    _IMG_TAG = re.compile(r"!\[[^\]]*\]\([^)]+\)")
    _FIG_REF = re.compile(r"\bFigura\b", re.IGNORECASE)

    for i, block in enumerate(blocks):
        if not block.is_context_stem:
            continue
        if not _FIG_REF.search(block.raw_markdown):
            continue
        if _IMG_TAG.search(block.raw_markdown):
            continue  # already has its own images

        # Collect images from sibling blocks in the same group
        collected_imgs: list[str] = []       # raw ![]() markdown tags
        collected_paths: list[str] = []      # image paths only

        for j in range(i + 1, len(blocks)):
            if blocks[j].numero_principal != block.numero_principal:
                break
            imgs = _IMG_TAG.findall(blocks[j].raw_markdown)
            if not imgs:
                continue
            collected_imgs.extend(imgs)
            collected_paths.extend(
                re.findall(r"!\[[^\]]*\]\(([^)]+)\)", blocks[j].raw_markdown)
            )
            # Remove images from sibling raw_markdown
            blocks[j].raw_markdown = _IMG_TAG.sub("", blocks[j].raw_markdown).strip()
            blocks[j].imagens = re.findall(
                r"!\[[^\]]*\]\(([^)]+)\)", blocks[j].raw_markdown
            )

        if collected_imgs:
            blocks[i].raw_markdown = (
                blocks[i].raw_markdown.rstrip()
                + "\n\n"
                + "\n".join(collected_imgs)
            )
            blocks[i].imagens = collected_paths
            blocks[i].imagens_contexto = collected_paths

    return blocks


def _assign_section_contexts(
    markdown_text: str,
    blocks: list[MarkdownQuestionBlock],
) -> list[MarkdownQuestionBlock]:
    """Associa textos de secção (PARTE A/B/C, GRUPO II/III) como contexto de cada questão.

    Para cada secção delimitada por cabeçalhos # PARTE X ou # GRUPO X, extrai o texto
    que precede a primeira questão numerada e atribui-o a `section_context` de todos
    os blocos dessa secção que não sejam context_stem nem já tenham contexto de item pai.
    Só activa quando o texto da secção tem ≥ 150 caracteres (evita cabeçalhos vazios).
    """
    section_starts = sorted(
        [m.start() for m in _GRUPO_HEADING_RE.finditer(markdown_text)]
        + [m.start() for m in _PARTE_HEADING_RE.finditer(markdown_text)]
    )
    if not section_starts:
        return blocks

    lines = markdown_text.splitlines(keepends=True)
    cumlen = [0]
    for line in lines:
        cumlen.append(cumlen[-1] + len(line))

    def line_to_char(line_num: int) -> int:
        idx = max(0, line_num - 1)
        return cumlen[min(idx, len(cumlen) - 1)]

    block_chars = [line_to_char(b.source_span.get("line_start", 1)) for b in blocks]

    sections: list[tuple[int, int, str]] = []
    for i, sec_start in enumerate(section_starts):
        sec_end = section_starts[i + 1] if i + 1 < len(section_starts) else len(markdown_text)
        first_q_char = sec_end
        for char_pos in block_chars:
            if sec_start <= char_pos < sec_end:
                first_q_char = min(first_q_char, char_pos)
        ctx = markdown_text[sec_start:first_q_char].strip()
        if len(ctx) >= 150:
            sections.append((sec_start, sec_end, ctx))

    context_stem_numbers: set[int] = {b.numero_principal for b in blocks if b.is_context_stem}

    for block, char_pos in zip(blocks, block_chars):
        if block.is_context_stem:
            continue
        if block.numero_principal in context_stem_numbers:
            continue
        for sec_start, sec_end, ctx in sections:
            if sec_start <= char_pos < sec_end:
                block.section_context = ctx
                break

    return blocks


def split_markdown_question_blocks(markdown_text: str) -> list[MarkdownQuestionBlock]:
    # Fix OCR artefact: subitem heading fused inline after other content.
    # e.g. "...fórmula \* 13.1. Qual é..." → "...fórmula\n\n13.1. Qual é..."
    # The \* (escaped asterisk) acts as a separator in some PDFs.
    markdown_text = re.sub(
        r"\s+\\[*]\s+(\d{1,3}\.\d{1,2}\.)\s+",
        r"\n\n\1 ",
        markdown_text,
    )
    # Fix OCR artefact: main item heading fused inline — "\* 9. Sejam..." → "\n\n\* 9. Sejam..."
    markdown_text = re.sub(
        r"([^\n])\n(\\[*]\s+\d{1,3}\.)",
        r"\1\n\n\2",
        markdown_text,
    )

    # Fix MinerU LaTeX artefacts in display math — applies to already-extracted markdown
    # so we can re-run Module 2 without re-running the slow Module 1.
    def _fix_array_colspec(m: re.Match) -> str:
        return r"\begin{array}{" + m.group(1).replace(" ", "") + "}"
    markdown_text = re.sub(r"\\begin\{array\}\s*\{([^}]*)\}", _fix_array_colspec, markdown_text)
    markdown_text = re.sub(
        r"\\mathrm\{\s*([A-Za-z](?:\s+[A-Za-z])*)\s*\}",
        lambda m: r"\text{" + m.group(1).replace(" ", "") + "}",
        markdown_text,
    )
    markdown_text = re.sub(r"(\\right\.)\s*\}(\s*\n\$\$)", r"\1\2", markdown_text)

    roman_matches = list(_ROMAN_PREFIX_QUESTION_RE.finditer(markdown_text))
    matches = roman_matches if roman_matches else list(QUESTION_HEADING_PATTERN.finditer(markdown_text))
    if not matches:
        stripped = markdown_text.strip()
        if not stripped:
            return []
        return [
            MarkdownQuestionBlock(
                ordem_item=1,
                item_id="1",
                numero_principal=1,
                subitem=None,
                heading_label_raw="1",
                raw_markdown=stripped,
                imagens=extract_image_paths(stripped),
                imagens_contexto=extract_image_paths(stripped),
                source_span={"line_start": 1, "line_end": stripped.count("\n") + 1},
                inferred_type=infer_question_type(stripped),
            )
        ]

    normalized = _normalize_heading_sequence([match.group("label") for match in matches])
    block_specs: list[tuple[int, int, str, int, str | None, str, bool]] = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        if not markdown_text[start:end].strip():
            continue
        item_id, main_number, subitem, suspected_reset = normalized[index]
        block_specs.append(
            (
                start,
                end,
                item_id,
                main_number,
                subitem,
                match.group("label"),
                suspected_reset,
            )
        )
    block_specs = _inject_missing_parent_blocks(markdown_text, block_specs)
    block_specs = _expand_inline_subheadings(markdown_text, block_specs)
    blocks = _expand_implicit_boundaries(markdown_text, block_specs)
    blocks = _mark_context_stems(blocks)
    blocks = _redistribute_images_by_reference(blocks)

    # ── Atribuir grupo (Grupo I / II / …) ────────────────────────────────────
    grupo_matches = list(_GRUPO_HEADING_RE.finditer(markdown_text))
    if grupo_matches:
        # Construir lista ordenada de (posição_no_texto, grupo_romano)
        grupo_breakpoints: list[tuple[int, str]] = [
            (m.start(), _ROMANO_CANON.get(m.group("num").upper(), m.group("num").upper()))
            for m in grupo_matches
        ]
        lines = markdown_text.splitlines(keepends=True)
        for block in blocks:
            pos = block.source_span.get("line_start", 0)
            # Converter linha → posição aproximada no texto (contar chars até essa linha)
            char_pos = sum(len(l) for l in lines[: pos - 1]) if pos > 1 else 0
            # Grupo ativo = último breakpoint antes desta posição
            grupo_ativo = ""
            for bp_pos, bp_grupo in grupo_breakpoints:
                if bp_pos <= char_pos:
                    grupo_ativo = bp_grupo
            block.grupo = grupo_ativo

        # Renumerar id_item para ser relativo ao grupo (ex: II-9 → II-1, II-10.1 → II-2.1)
        group_min_main: dict[str, int] = {}
        for block in blocks:
            if block.grupo and block.subitem is None:
                main = block.numero_principal
                if block.grupo not in group_min_main or main < group_min_main[block.grupo]:
                    group_min_main[block.grupo] = main

        for block in blocks:
            if block.grupo:
                offset = group_min_main.get(block.grupo, 1) - 1
                if offset > 0:
                    if "." in block.item_id:
                        main_part, sub_part = block.item_id.split(".", 1)
                        block.item_id = f"{int(main_part) - offset}.{sub_part}"
                    else:
                        block.item_id = str(int(block.item_id) - offset)
                # Prefixar id_item com grupo: "1" → "I-1", "2.1" → "II-2.1"
                if not block.item_id.startswith(block.grupo + "-"):
                    block.item_id = f"{block.grupo}-{block.item_id}"

    blocks = _assign_section_contexts(markdown_text, blocks)
    return blocks


def split_markdown_questions(markdown_text: str) -> list[tuple[int, str]]:
    return [
        (block.numero_principal, block.raw_markdown)
        for block in split_markdown_question_blocks(markdown_text)
    ]
