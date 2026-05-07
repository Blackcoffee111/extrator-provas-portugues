from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess


# Detetar cabeçalhos de grupo: "# Grupo I", "## GRUPO II", "# Grupo III", etc.
_GRUPO_HEADING_RE = re.compile(
    r"(?m)^#{1,3}\s*[Gg][Rr][Uu][Pp][Oo]\s+(?P<num>I{1,3}|IV|VI{0,3}|IX|X)\b"
)
# Detetar cabeçalhos de PARTE (Português):
#   "## PARTE A", "## Parte B", etc.   — convenção MinerU clássica.
#   "## A", "### B", etc.              — convenção IAVE/Sonnet 4.6 (apenas a
#       letra, isolada na linha — assume-se inserida dentro de um GRUPO X).
_PARTE_HEADING_RE = re.compile(
    r"(?m)^#{1,3}\s+(?:[Pp][Aa][Rr][Tt][Ee]\s+(?P<letra>[A-C])"
    r"|(?P<letra_short>[A-C]))\s*$"
)


def _parte_letra(m: "re.Match[str]") -> str:
    """Extrai a letra de PARTE de um match de _PARTE_HEADING_RE.

    Suporta ambas as variantes do regex: '## PARTE A' e '## A'.
    """
    return ((m.group("letra") if "letra" in m.groupdict() else None)
            or (m.group("letra_short") if "letra_short" in m.groupdict() else None)
            or "").upper()
# Notas de rodapé do excerto: "¹ calamistrar – tornar crespo"  ou  "1 calamistrar – ..."
# Requisitos: (1) traço separador (— ou – ou " - ") entre o termo e a definição;
# (2) o texto antes do traço tem ≤40 chars e não contém ; : ( ) — exclui linhas de prosa longas
# que contêm " - " incidentalmente (ex: "30 Telefones de...; sócio... - porque").
_NOTA_RODAPE_RE = re.compile(
    r"(?m)^(?P<num>[¹²³⁴⁵⁶⁷⁸⁹\d]{1,2})\s+(?P<texto>[A-ZÁÀÂÃÉÊÍÓÔÕÚÇa-záàâãéêíóôõúç][^;:()\n]{0,38}(?:—|–| - )[^\n]+?)$"
)
# Marcador de item opcional (asterisco, ★, * no início da linha de questão)
_OPCIONAL_MARKER_RE = re.compile(r"^\s*(?:\*\s*|\★\s*|\\bigstar\s*|\$\\(?:star|bigstar|ast)\$\s*)")
# Quadros de completar — linha iniciada por "(a)" ou com "a)" ... "b)" em Português PT
_COMPLETE_TABLE_STEM_RE = re.compile(
    r"\b(?:complete\s+as?\s+afirma[çc][oõ]es|selecione\s+a\s+op[çc][aã]o\s+adequada)\b",
    re.IGNORECASE,
)
# Multi-select (as três afirmações verdadeiras, etc.)
_MULTI_SELECT_STEM_RE = re.compile(
    r"\b(?:tr[êe]s\s+afirma[çc][oõ]es\s+verdadeiras|identifique\s+as\s+(?:tr[êe]s|duas|quatro))\b",
    re.IGNORECASE,
)
# Dissertação (Grupo III)
_ESSAY_STEM_RE = re.compile(
    r"\b(?:num\s+texto\s+de\s+opini[aã]o|escreva\s+uma\s+(?:breve\s+)?exposi[çc][aã]o|redija\s+um\s+texto)\b",
    re.IGNORECASE,
)
# Mapa de numeral romano → string canónica
_ROMANO_CANON = {"I": "I", "II": "II", "III": "III", "IV": "IV", "V": "V",
                 "VI": "VI", "VII": "VII", "VIII": "VIII", "IX": "IX", "X": "X"}

IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
QUESTION_HEADING_PATTERN = re.compile(
    r"(?m)^(?:\$\\(?:star|bigstar|ast)\$\s*|\$?\\pm\s*|\\[*]\s*|[\*\u00b1•-]\s*|\*\*\s*)?"
    r"(?:Quest[aã]o\s+)?"
    r"(?P<label>\d{1,3}(?:\.\d{1,2})?)"
    r"(?:\s*\.\s*(?:\*\*)?\s*\$?\s+|\s*\.\*\*\s+|(?=[A-ZÁÉÍÓÚÀÂÃÇ]))"
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
    parte: str = ""          # "A", "B", "C" — vazio quando não há subdivisão PT
    pool_opcional: str = ""  # "I-opt", "II-opt" — vazio = item obrigatório


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
    "EE": "Época Especial",
}

# EX-MatA635-F1-2024_net  ou  EX-MatA635-EE-2021_net  ou  EX-MatA635-F1-2024-CC-VD
_FONTE_PATTERN = re.compile(
    r"EX-(?P<materia>[A-Za-z]+)\d*-(?P<fase>(?:EE|F\w+))-(?P<ano>\d{4})",
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
    if _ESSAY_STEM_RE.search(markdown_block):
        return "essay"
    if _MULTI_SELECT_STEM_RE.search(markdown_block):
        return "multi_select"
    if _COMPLETE_TABLE_STEM_RE.search(markdown_block):
        return "complete_table"
    if COMPLETION_PATTERN.search(markdown_block):
        return "completion"
    return "open_response"


def is_optional_marker(line: str) -> bool:
    """Verifica se uma linha começa com um marcador de item opcional (★, *)."""
    return bool(_OPCIONAL_MARKER_RE.match(line))


def extract_notas_rodape(text: str) -> list[dict]:
    """Extrai notas de rodapé de um bloco de texto (após o excerto/poema).

    Devolve lista de {"numero": "1", "texto": "calamistrar – tornar crespo"}.
    """
    notas = []
    for m in _NOTA_RODAPE_RE.finditer(text):
        # Normalizar número (converter superscript unicode para algarismo)
        raw_num = m.group("num")
        num = raw_num.translate(str.maketrans("¹²³⁴⁵⁶⁷⁸⁹", "123456789"))
        notas.append({"numero": num, "texto": m.group("texto").strip()})
    return notas


def strip_notas_section(text: str) -> str:
    """Remove a secção de notas de rodapé do final do texto do excerto/poema.

    Após extrair as notas com extract_notas_rodape, chama esta função para
    limpar o enunciado — as notas ficam apenas em observacoes, não duplicadas
    no corpo do texto.
    """
    lines = text.splitlines()
    # Encontrar o primeiro índice de linha que é uma nota de rodapé
    first_nota = None
    for i, ln in enumerate(lines):
        if _NOTA_RODAPE_RE.match(ln.strip()):
            first_nota = i
            break
    if first_nota is None:
        return text
    # Manter tudo antes da primeira nota; remover linhas em branco antes dela
    trimmed = "\n".join(lines[:first_nota]).rstrip()
    return trimmed


# Frases boilerplate que podem aparecer isoladas num preâmbulo de grupo/parte
# e não devem originar um context_stem. Comparação literal após strip.
_PT_PREAMBLE_BOILERPLATE: tuple[str, ...] = (
    "Apresente as suas respostas de forma bem estruturada.",
    "Para cada resposta, identifique o grupo e o item.",
    "Utilize apenas caneta ou esferográfica de tinta azul ou preta.",
    "Não é permitido o uso de corretor. Risque aquilo que pretende que não seja classificado.",
    "Não é permitida a consulta de dicionário.",
    "Apresente apenas uma resposta para cada item.",
    "As cotações dos itens encontram-se no final do enunciado da prova.",
)


def _strip_pt_boilerplate(preamble: str) -> str:
    """Remove frases boilerplate de instruções ao aluno no preâmbulo PT."""
    cleaned = preamble
    for phrase in _PT_PREAMBLE_BOILERPLATE:
        cleaned = cleaned.replace(phrase, "")
    # Colapsar linhas em branco e espaços resultantes
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_pt_group_contexts(
    markdown_text: str,
    blocks: "list[MarkdownQuestionBlock]",
) -> dict[tuple[str, str], str]:
    """Extrai texto de preâmbulo (excerto, intro) antes do 1.º item de cada (grupo, parte).

    Usado apenas para provas de Português. Devolve dict (grupo, parte) → texto.
    Semântica das chaves:
    - ("I", "")  = texto entre # GRUPO I e ## PARTE A (= excerto literário)
    - ("I", "A") = texto entre ## PARTE A e 1.ª questão de PARTE A (geralmente vazio)
    - ("II", "") = texto entre # GRUPO II e 1.ª questão (= texto expositivo)
    - ("III","") = texto entre # GRUPO III e 1.ª questão (= tema de dissertação)
    """
    if not blocks:
        return {}

    lines = markdown_text.splitlines(keepends=True)

    def _char_pos(line_no: int) -> int:
        return sum(len(l) for l in lines[: line_no - 1]) if line_no > 1 else 0

    # Eventos ordenados: (heading_start, text_start, grupo, parte)
    all_events: list[tuple[int, int, str, str]] = []
    grupo_current = ""
    parte_current = ""
    for m in sorted(
        [*_GRUPO_HEADING_RE.finditer(markdown_text), *_PARTE_HEADING_RE.finditer(markdown_text)],
        key=lambda m: m.start(),
    ):
        line_end = markdown_text.find("\n", m.start())
        text_start = line_end + 1 if line_end >= 0 else len(markdown_text)
        gd = m.groupdict()
        if gd.get("num") is not None:
            grupo_current = _ROMANO_CANON.get(gd["num"].upper(), gd["num"].upper())
            parte_current = ""
        else:
            parte_current = _parte_letra(m)
        all_events.append((m.start(), text_start, grupo_current, parte_current))

    if not all_events:
        return {}

    # Posição do 1.º bloco de cada (grupo, parte)
    first_block_char: dict[tuple[str, str], int] = {}
    for block in blocks:
        key = (block.grupo, block.parte)
        cpos = _char_pos(block.source_span.get("line_start", 1))
        if key not in first_block_char or cpos < first_block_char[key]:
            first_block_char[key] = cpos

    result: dict[tuple[str, str], str] = {}
    for i, (heading_start, text_start, grupo, parte) in enumerate(all_events):
        next_boundary = all_events[i + 1][0] if i + 1 < len(all_events) else len(markdown_text)
        first_q = first_block_char.get((grupo, parte), next_boundary)
        preamble_end = min(next_boundary, first_q)
        preamble = markdown_text[text_start:preamble_end].strip()
        # Remover sub-cabeçalhos que possam ter ficado no intervalo
        preamble = re.sub(r"(?m)^#{1,4}[^\n]*\n?", "", preamble).strip()
        preamble = _strip_pt_boilerplate(preamble)
        if len(preamble) > 30:
            result[(grupo, parte)] = preamble

    return result


def detect_partes(markdown_text: str) -> list[tuple[int, str]]:
    """Retorna lista de (char_offset, letra_parte) para os cabeçalhos PARTE A/B/C.

    Aceita 'PARTE A' (MinerU) e a forma reduzida '# A'/'## A' (Sonnet/IAVE).
    """
    return [
        (m.start(), _parte_letra(m))
        for m in _PARTE_HEADING_RE.finditer(markdown_text)
        if _parte_letra(m)
    ]


# ---------------------------------------------------------------------------
# Normalização defensiva do markdown PT antes do splitter de questões.
#
# Cobre 3 problemas que o sub-agente Sonnet pode produzir em provas antigas:
#
#  (P5) Partes A/B/C sem heading marker — em provas pré-2024 a margem do PDF
#       mostra apenas a letra ("B") sem "Parte B" nem cabeçalho visual claro.
#       Sonnet pode então emiti-la como linha solta `B` ou `**B**`, sem `##`.
#       O texto da parte fica então fundido com a questão anterior. Promove-se
#       a `## B` quando a letra está sozinha numa linha dentro de um GRUPO já
#       activo e a sequência (A → B → C) é coerente.
#
#  (P2) Observações `1.`/`2.` confundidas com questões — o GRUPO III tem uma
#       secção "**Observações:**" no fim com itens enumerados `1.` `2.` que o
#       parser de questões captura como itens reais. A normalização re-escreve
#       essas linhas como `(1)` `(2)` para neutralizar o splitter.
# ---------------------------------------------------------------------------

# Linha contendo APENAS A/B/C (com ou sem **bold**), sem heading marker.
_LONE_PART_LETTER_RE = re.compile(
    r"(?m)^[ \t]*(?:\*\*\s*)?(?P<letra>[A-C])(?:\s*\*\*)?[ \t]*$"
)

# Início da secção Observações (negrito ou rótulo simples).
_OBSERVACOES_RE = re.compile(
    r"(?mi)^[ \t]*(?:\*\*)?\s*Observa[çc][oõ]es\s*:?\s*(?:\*\*)?[ \t]*$"
)

# Linha "N. texto..." (com ou sem **) para reescrever como "(N) texto..."
# `[ \t]*` em vez de `\s*` para NÃO atravessar `\n` — caso contrário, o
# `\s*` antes de `\d` consome as linhas em branco que separam Observações.
_NUMBERED_OBS_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)(?:\*\*)?[ \t]*(?P<num>\d{1,2})[ \t]*\.[ \t]*(?:\*\*)?[ \t]+(?P<rest>.+)$"
)


def normalize_pt_prova_markdown(markdown_text: str) -> str:
    """Aplica normalizações defensivas em provas PT antes do splitter.

    Idempotente: passar o resultado pela função de novo não altera nada.
    """
    text = markdown_text

    # ── (P5) promover letras de Parte isoladas a `## A`/`## B`/`## C` ──────
    # Só promove se:
    #   • a linha contém APENAS A/B/C (com ou sem **)
    #   • estamos dentro de um GRUPO (já vimos `# GRUPO X`)
    #   • ainda não há `## <letra>` activo para esta letra no GRUPO actual
    #   • a letra avança a sequência esperada (A primeiro, depois B, depois C)
    # Implementação linha-a-linha — mais legível que regex global.
    out_lines: list[str] = []
    in_grupo = False
    seen_partes: set[str] = set()  # letras já promovidas dentro do grupo actual
    for line in text.splitlines():
        if _GRUPO_HEADING_RE.match(line):
            in_grupo = True
            seen_partes = set()
            out_lines.append(line)
            continue
        # Já é cabeçalho de PARTE? Marcar como vista, não promover.
        m_parte = _PARTE_HEADING_RE.match(line)
        if m_parte:
            seen_partes.add(_parte_letra(m_parte))
            out_lines.append(line)
            continue
        # Candidato a promoção?
        m_lone = _LONE_PART_LETTER_RE.match(line)
        if in_grupo and m_lone:
            letra = m_lone.group("letra").upper()
            # Promove se a letra ainda não foi vista neste GRUPO E avança a
            # sequência. (A primeiro; B só se A já vista ou se for a primeira;
            # C só se B já vista.)
            expected_next = "A" if not seen_partes else (
                "B" if "A" in seen_partes and "B" not in seen_partes else (
                    "C" if "B" in seen_partes and "C" not in seen_partes else None
                )
            )
            if letra == expected_next:
                out_lines.append(f"## {letra}")
                seen_partes.add(letra)
                continue
        out_lines.append(line)
    text = "\n".join(out_lines)

    # ── (P2) Re-escrever Observações: 1./2. → (1)/(2) ──────────────────────
    # Detectar a posição de "**Observações:**" e reescrever apenas as linhas
    # numeradas que aparecem entre essa âncora e o próximo cabeçalho `#`/`##`.
    obs_match = _OBSERVACOES_RE.search(text)
    if obs_match:
        before = text[: obs_match.end()]
        rest = text[obs_match.end():]
        # Encontrar próximo cabeçalho (#) que termina a secção Observações
        next_heading = re.search(r"(?m)^#{1,3}\s", rest)
        cut = next_heading.start() if next_heading else len(rest)
        obs_section = rest[:cut]
        tail = rest[cut:]
        # Reescrever linhas "N. ..." → "(N) ..."
        obs_section = _NUMBERED_OBS_RE.sub(
            lambda m: f"{m.group('indent')}({m.group('num')}) {m.group('rest')}",
            obs_section,
        )
        text = before + obs_section + tail

    return text


def synthesize_grupo_iii_essay_block(
    markdown_text: str, existing_blocks: list[MarkdownQuestionBlock]
) -> MarkdownQuestionBlock | None:
    """Cria bloco sintético `III-1` quando GRUPO III existe sem item numerado.

    Em provas antigas a dissertação do GRUPO III não tem número visível no
    PDF; Sonnet/MinerU podem então não emitir um cabeçalho de questão. Este
    fallback garante que `III-1` é sempre criado a partir do conteúdo do grupo.

    Devolve `None` se:
      • não houver `# GRUPO III` no markdown, ou
      • já existir pelo menos um bloco com grupo == "III".
    """
    grupo_iii = None
    for m in _GRUPO_HEADING_RE.finditer(markdown_text):
        if _ROMANO_CANON.get(m.group("num").upper(), "") == "III":
            grupo_iii = m
            break
    if grupo_iii is None:
        return None
    # Já existe algum bloco em GRUPO III? Aproximação: bloco cuja posição
    # source_span começa depois de # GRUPO III.
    grupo_iii_start_line = markdown_text[: grupo_iii.start()].count("\n") + 1
    for block in existing_blocks:
        if block.source_span.get("line_start", 0) >= grupo_iii_start_line:
            # Há conteúdo numerado depois de # GRUPO III — não sintetizar.
            return None
    # Extrair conteúdo do GRUPO III (do fim do heading até COTAÇÕES ou EOF).
    body_start = grupo_iii.end()
    cot_match = re.search(r"(?m)^#{1,3}\s*COTA[ÇC][ÕO]ES\b", markdown_text)
    body_end = cot_match.start() if cot_match and cot_match.start() > body_start else len(markdown_text)
    body = markdown_text[body_start:body_end].strip()
    if not body:
        return None
    end_line = grupo_iii_start_line + body.count("\n")
    return MarkdownQuestionBlock(
        ordem_item=0,  # ajustado por chamadores
        item_id="III-1",
        numero_principal=1,
        subitem=None,
        heading_label_raw="1",
        raw_markdown=body,
        imagens=extract_image_paths(body),
        imagens_contexto=extract_image_paths(body),
        source_span={"line_start": grupo_iii_start_line + 1, "line_end": end_line},
        inferred_type="essay",
        grupo="III",
    )


# ---------------------------------------------------------------------------
# Normalização de números de linha em preâmbulos de Português
# ---------------------------------------------------------------------------
# O MinerU pode OCRizar números de linha de um excerto/texto expositivo de
# formas distintas:
#   (a) "5 calamistrar" — sem ponto → sobrevive intacto ao splitter.
#   (b) "5. No entanto" — com ponto → é visto pelo splitter como cabeçalho
#       de questão e o prefixo "5. " é removido, perdendo-se o marcador.
#   (c) "0 ser bela" — "10" partido pela quebra de coluna (dígito 1 sumiu).
#   (d) "...máscara. 5 É-se... melhor. 10 Assim" — poema colapsado numa só
#       linha com números de verso inline.
#
# Esta normalização corrige (b), (c) e (d) dentro de preâmbulos PT, antes
# do splitter de blocos actuar. Nada inventa: apenas move ou tira caracteres
# já presentes no markdown.

_PT_LINE_NUM_WITH_DOT_RE = re.compile(
    r"(?m)^(?P<num>5|10|15|20|25|30|35|40|45|50|55|60|65|70|75|80|85|90|95)"
    r"\.\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚa-záàâãéêíóôõúç«])"
)

_PT_BROKEN_TEN_RE = re.compile(
    r"(?m)^0\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚa-záàâãéêíóôõúç])"
)

_PT_INLINE_LINE_NUM_RE = re.compile(
    r"(?<=[\.\!\?»…])\s+"
    r"(?P<num>5|10|15|20|25|30|35|40|45|50|55|60|65|70|75|80|85|90|95)"
    r"\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚÉ])"
)

# Marca o fim da zona de preâmbulo dentro de um grupo: "1. Texto..." em linha.
_PT_FIRST_REAL_QUESTION_RE = re.compile(
    r"(?m)^1\.\s+[A-ZÁÀÂÃÉÊÍÓÔÕÚ(«]"
)


def _fix_broken_tens(preamble: str) -> str:
    """Repõe o dígito inicial truncado em '0 texto' → '10 texto', '20 texto', …

    Usa os outros números já válidos no preâmbulo para inferir a progressão.
    Só converte se for possível deduzir sem ambiguidade.
    """
    lines = preamble.splitlines(keepends=True)
    known: list[tuple[int, int]] = []  # (idx_linha, valor)
    for i, line in enumerate(lines):
        m = re.match(r"^(\d{1,3})\s", line)
        if m:
            val = int(m.group(1))
            if val % 5 == 0 and 5 <= val <= 99:
                known.append((i, val))

    if not known:
        return preamble

    out = list(lines)
    for i, line in enumerate(lines):
        if not re.match(r"^0\s", line):
            continue
        prev_val = next_val = None
        for idx, val in known:
            if idx < i:
                prev_val = val
            elif idx > i and next_val is None:
                next_val = val
                break
        inferred: int | None = None
        if prev_val is not None and next_val is not None and next_val - prev_val == 10:
            inferred = prev_val + 5
        elif prev_val is not None and prev_val % 10 == 5:
            # progressão canónica 5 → 10, 15 → 20, …; '0' logo após "5" ou "15" é 10/20
            inferred = prev_val + 5
        elif next_val is not None and next_val % 10 == 5:
            inferred = next_val - 5
        if inferred is not None and inferred > 0 and inferred % 10 == 0:
            out[i] = re.sub(r"^0\s", f"{inferred} ", line, count=1)
    return "".join(out)


_PT_PROSE_LINE_NUM_CANDIDATE_RE = re.compile(
    r"(?<=\s)(?P<num>\d{1,2})(?=\s+[a-záàâãéêíóôõúçA-ZÁÀÂÃÉÊÍÓÔÕÚÇ«])"
)


def _restore_prose_line_numbers(preamble: str) -> str:
    """Insere quebra de linha antes de números de verso fundidos em prosa.

    Em excertos narrativos o OCR colapsa marcadores de linha (5, 10, 15, …)
    no meio de frases porque as colunas PDF não têm pontuação a separá-los —
    o detector `_break_inline_line_numbers` (pensado para poesia) não aplica
    aqui. Esta heurística é conservadora:

      * Só aceita múltiplos de 5 em [5, 95].
      * O baseline é o primeiro múltiplo de 5 encontrado em início de linha
        (não se assume que a numeração começa em 5 — em GRUPO II do texto
        expositivo, pode começar em 15, por exemplo).
      * Exige sequência monótona: só trata `N` como marcador se for o próximo
        esperado (current+5) — avança pelo baseline dos já-em-início-de-linha.
      * Não toca num número que já esteja em início de linha.
    """
    if not preamble:
        return preamble
    expected: int | None = None
    out: list[str] = []
    pos = 0
    for m in _PT_PROSE_LINE_NUM_CANDIDATE_RE.finditer(preamble):
        val = int(m.group("num"))
        if val % 5 != 0 or val < 5 or val > 95:
            continue
        line_start = preamble.rfind("\n", 0, m.start()) + 1
        at_line_start = preamble[line_start:m.start()].strip() == ""
        if expected is None:
            # Primeiro candidato define o baseline. Só aceitamos se estiver
            # em início de linha (senão não há sinal de que é mesmo marcador).
            if at_line_start:
                expected = val + 5
            continue
        if val != expected:
            continue
        if at_line_start:
            expected = val + 5
            continue
        out.append(preamble[pos:m.start()])
        out.append("\n")
        out.append(m.group("num"))
        pos = m.end()
        expected = val + 5
    out.append(preamble[pos:])
    return "".join(out)


def _break_inline_line_numbers(preamble: str) -> str:
    """Se uma mesma linha contiver ≥2 números de verso inline, insere '\\n' antes deles.

    Evita falsos positivos (ex.: números isolados num texto em prosa) exigindo 2+
    ocorrências na mesma linha física — padrão típico de poema colapsado.
    """
    out_lines: list[str] = []
    for line in preamble.splitlines(keepends=True):
        matches = list(_PT_INLINE_LINE_NUM_RE.finditer(line))
        if len(matches) < 2:
            out_lines.append(line)
            continue
        new_line = _PT_INLINE_LINE_NUM_RE.sub(
            lambda m: f"\n{m.group('num')} ", line
        )
        out_lines.append(new_line)
    return "".join(out_lines)


def normalize_pt_preamble_line_numbers(markdown_text: str) -> str:
    """Repara números de linha nos preâmbulos e excertos de provas PT.

    Três correcções:
      1. "N. TEXTO" com N múltiplo de 5 → "N TEXTO" — só dentro da zona de
         preâmbulo (entre "# GRUPO X" e a 1.ª questão "1. …") e só se a zona
         tiver ≥2 candidatos (evita atingir questões como "5. Depois…").
      2. "0 TEXTO" → "10/20/… TEXTO" — restaura dígito truncado em quebra de
         coluna, dentro da mesma zona.
      3. Linha única com ≥2 números de verso inline → insere "\\n" antes de cada
         (aplicada globalmente: o requisito de ≥2 ocorrências já evita falsos
         positivos em prosa comum).
    """
    result = markdown_text

    grupo_starts = [m.start() for m in _GRUPO_HEADING_RE.finditer(result)]
    if grupo_starts:
        boundaries = grupo_starts + [len(result)]
        chunks: list[str] = [result[: boundaries[0]]]

        for i in range(len(grupo_starts)):
            group_start = boundaries[i]
            group_end = boundaries[i + 1]
            group_text = result[group_start:group_end]

            q_match = _PT_FIRST_REAL_QUESTION_RE.search(group_text)
            preamble_end = q_match.start() if q_match else len(group_text)
            preamble = group_text[:preamble_end]
            rest = group_text[preamble_end:]

            dot_candidates = _PT_LINE_NUM_WITH_DOT_RE.findall(preamble)
            if len(dot_candidates) >= 2:
                preamble = _PT_LINE_NUM_WITH_DOT_RE.sub(
                    lambda m: f"{m.group('num')} ", preamble
                )
            preamble = _fix_broken_tens(preamble)
            preamble = _restore_prose_line_numbers(preamble)

            chunks.append(preamble)
            chunks.append(rest)
        result = "".join(chunks)

    result = _break_inline_line_numbers(result)
    return result


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


def split_markdown_question_blocks(markdown_text: str) -> list[MarkdownQuestionBlock]:
    # Normalização defensiva PT: promove letras de PARTE isoladas a `## A`/`## B`
    # e reescreve "Observações: 1." → "Observações: (1)" para evitar que o
    # splitter capture pseudo-itens. Idempotente.
    markdown_text = normalize_pt_prova_markdown(markdown_text)

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

    matches = list(QUESTION_HEADING_PATTERN.finditer(markdown_text))
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

    # Fronteiras estruturais (# GRUPO X, # PARTE A/B/C) para capar o fim de cada
    # bloco de questão. Sem isto, a última questão de uma parte captura o preâmbulo
    # inteiro da parte seguinte (poema, texto expositivo, etc.) até à próxima
    # questão numerada.
    _structural_boundaries = sorted(
        [m.start() for m in _GRUPO_HEADING_RE.finditer(markdown_text)]
        + [m.start() for m in _PARTE_HEADING_RE.finditer(markdown_text)]
    )

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        for _bpos in _structural_boundaries:
            if start < _bpos < end:
                end = _bpos
                break
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

    # ── Marcar itens opcionais (★ / * antes do número de questão) ────────────
    # O MinerU pode renderizar ★ como "$\bigstar$", "★" ou "*".
    # Procuramos o marcador na primeira linha do raw_markdown de cada bloco.
    _opcional_pools: dict[str, int] = {}  # grupo → contador de itens opcionais
    for block in blocks:
        first_line = block.raw_markdown.split("\n")[0]
        if is_optional_marker(first_line):
            pool_key = f"{block.grupo}-opt" if block.grupo else "opt"
            _opcional_pools.setdefault(pool_key, 0)
            block.pool_opcional = pool_key

    # ── Atribuir PARTE (A/B/C) para Grupos com subdivisões PT ────────────────
    parte_breakpoints = detect_partes(markdown_text)
    if parte_breakpoints:
        # Combinar breakpoints de GRUPO e PARTE em ordem; GRUPO reseta a parte ativa
        _grupo_bps: list[tuple[int, str | None]] = [
            (m.start(), None)  # None = sinal de reset de parte
            for m in _GRUPO_HEADING_RE.finditer(markdown_text)
        ]
        _parte_bps: list[tuple[int, str | None]] = [
            (pos, letra) for pos, letra in parte_breakpoints
        ]
        _all_bps: list[tuple[int, str | None]] = sorted(
            _grupo_bps + _parte_bps, key=lambda x: x[0]
        )
        lines = markdown_text.splitlines(keepends=True)
        for block in blocks:
            pos = block.source_span.get("line_start", 0)
            char_pos = sum(len(l) for l in lines[: pos - 1]) if pos > 1 else 0
            parte_ativa = ""
            for bp_pos, bp_val in _all_bps:
                if bp_pos <= char_pos:
                    if bp_val is None:
                        parte_ativa = ""   # novo GRUPO reseta a parte
                    else:
                        parte_ativa = bp_val
            block.parte = parte_ativa
            if parte_ativa:
                # Prefixar id_item com a PARTE: "I-1" → "I-A-1"
                # Só aplicar se o id_item ainda não contém a parte
                parts_of_id = block.item_id.split("-")
                has_parte = (
                    len(parts_of_id) >= 2 and parts_of_id[1] in ("A", "B", "C")
                ) or (
                    len(parts_of_id) >= 1 and parts_of_id[0] in ("A", "B", "C")
                )
                if not has_parte:
                    if block.grupo and block.item_id.startswith(block.grupo + "-"):
                        suffix = block.item_id[len(block.grupo) + 1:]
                        block.item_id = f"{block.grupo}-{parte_ativa}-{suffix}"
                    else:
                        block.item_id = f"{parte_ativa}-{block.item_id}"

    # ── Fallback III-1: GRUPO III sem item numerado (ensaio sem cabeçalho) ───
    iii_block = synthesize_grupo_iii_essay_block(markdown_text, blocks)
    if iii_block is not None:
        iii_block.ordem_item = (max((b.ordem_item for b in blocks), default=0) + 1)
        blocks.append(iii_block)

    return blocks


def split_markdown_questions(markdown_text: str) -> list[tuple[int, str]]:
    return [
        (block.numero_principal, block.raw_markdown)
        for block in split_markdown_question_blocks(markdown_text)
    ]
