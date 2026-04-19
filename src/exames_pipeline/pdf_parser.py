from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import shutil
import shlex

from .config import Settings
from .utils import ensure_dir, run_command, slugify

# Importação lazy para evitar dependência circular e permitir uso sem settings
def _maybe_repair_ocr(settings: "Settings", pdf_path: "Path", markdown_path: "Path") -> None:
    """Tenta reparar marcadores OCR defeituosos. Silencioso em caso de falha."""
    try:
        from .module_ocr_repair import repair_ocr_markers  # noqa: PLC0415
        repair_ocr_markers(settings, pdf_path, markdown_path)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"[ocr_repair] Ignorado (erro inesperado): {exc}")


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
LATEX_FRAC_PATTERN = re.compile(r"\\frac\s*\{\s*([^{}]+?)\s*\}\s*\{\s*([^{}]+?)\s*\}")
LATEX_SUP_PATTERN = re.compile(r"(?P<base>(?:\\[A-Za-z]+|[A-Za-z0-9)\]]))\s*\^\s*\{\s*(?P<exp>[^{}]+?)\s*\}")
LATEX_SUB_PATTERN = re.compile(r"(?P<base>(?:\\[A-Za-z]+|[A-Za-z0-9)\]]))\s*_\s*\{\s*(?P<sub>[^{}]+?)\s*\}")
LATEX_CMD_SPACE_PATTERN = re.compile(r"\\(?P<cmd>[A-Za-z]+)\s+\{")
LATEX_FUNC_JOIN_PATTERN = re.compile(r"\\(?P<func>ln|sin|cos|tan|log|exp)(?P<arg>[A-Za-z0-9])")
LATEX_COMBINATORICS_PATTERN = re.compile(r"\^\s*(?P<sup>[0-9]+)\s*(?P<sym>[A-Z])_\{(?P<sub>[^{}]+)\}")
ESCAPED_QUESTION_STAR_PATTERN = re.compile(r"(?m)^\\\*\s*(?=\d+(?:\.\d+)*\.)")
DECORATIVE_STAR_PATTERN = re.compile(r"(?m)^\s*\$(?:\\star|\\ast|\\bigstar)\$+\s*(?=\d+(?:\.\d+)*\.)")
INLINE_STAR_NUMBER_PATTERN = re.compile(r"(?m)^\s*\$(?:\\star|\\ast|\\bigstar)\s*\\\s*(?P<num>\d+(?:\.\d+)*)\s*\.\$\s*")
LEADING_STAR_TOKEN_PATTERN = re.compile(r"(?m)^\s*\$(?:\\star|\\ast|\\bigstar)\$\s*")
QUESTION_SPACING_PATTERN = re.compile(r"(?m)^(?P<num>\d+(?:\.\d+)*)\.(?P<next>[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])")
BULLET_SPACING_PATTERN = re.compile(r"(?m)^•(?P<next>\S)")
# Número colado a letra maiúscula no início de linha sem ponto separador: "5Um grupo" → "5. Um grupo"
FUSED_NUMBER_TEXT_PATTERN = re.compile(r"(?m)^(?P<num>\d{1,3})(?P<next>[A-ZÁÀÂÃÉÊÍÓÔÕÚÇÀÈÌÒÙÂÊÎÔÛÄËÏÖÜ])")
# Subitem formatado como fórmula LaTeX: "$\pm 6 . 1 .$" → "6.1." / "$\pm 8 .$" → "8."
LATEX_PM_SUBITEM_PATTERN = re.compile(r"(?m)^\$\\pm\s*(?P<main>\d{1,3})\s*\.\s*(?P<sub>\d{1,2})\s*\.\s*\$")
LATEX_PM_ITEM_PATTERN = re.compile(r"(?m)^\$\\pm\s*(?P<num>\d{1,3})\s*\.\s*\$")
# Título da página de formulário — aceita variantes OCR com espaços entre letras e markdown opcional.
# Exemplos: "# FORMULÁRIOS", "F O R M U L Á R I O S", "**Formulário**"
_FORMULARIO_HEADING_RE = re.compile(
    r"(?im)^(?:#{1,4}\s+|\*{1,2})?F[\s]*O[\s]*R[\s]*M[\s]*[UÚ][\s]*L[\s]*[AÁ][\s]*R[\s]*I[\s]*[OÓ][\s]*S?(?:\*{1,2})?\s*$"
)
# Qualquer cabeçalho markdown (# a ####) no início de linha
_NEXT_HEADING_RE = re.compile(r"(?m)^#{1,4}\s+\S")


@dataclass(slots=True)
class ExtractionResult:
    pdf_path: Path
    output_dir: Path
    markdown_path: Path
    images_dir: Path
    parser_stdout: str
    parser_stderr: str
    simulated: bool


def _detect_mineru_binary(settings: Settings) -> str:
    candidates = [
        settings.mineru_binary,
        "mineru",
        str(settings.mineru_venv / "bin" / "mineru"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if Path(candidate).name == candidate else candidate
        if resolved and Path(resolved).exists():
            return str(Path(resolved))
        if Path(candidate).exists():
            return str(Path(candidate))
    return ""


def _detect_mineru_python(settings: Settings) -> str:
    candidates = [
        str(settings.mineru_venv / "bin" / "python"),
        str(settings.mineru_venv / "bin" / Path(settings.mineru_python_bin).name),
        settings.mineru_python_bin,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = shutil.which(candidate) if Path(candidate).name == candidate else candidate
        if resolved and Path(resolved).exists():
            return str(Path(resolved))
        if Path(candidate).exists():
            return str(Path(candidate))
    return ""


def _resolve_mineru_mode(settings: Settings, mineru_mode: str | None) -> str:
    mode = (mineru_mode or settings.mineru_mode or "light").strip().lower()
    if mode not in {"light", "full", "math_heavy"}:
        return "light"
    return mode


def _build_mineru_env(settings: Settings, mineru_mode: str) -> dict[str, str]:
    env = {
        "PYTHONPATH": str(settings.project_root / "src"),
        "MPLCONFIGDIR": str(settings.workdir / ".mplconfig"),
        "XDG_CACHE_HOME": str(settings.workdir / ".cache"),
        "YOLO_CONFIG_DIR": str(settings.workdir / ".ultralytics"),
        "MINERU_DISABLE_LAYOUTREADER": "1" if mineru_mode == "light" else "0",
    }
    if mineru_mode == "light":
        env["MINERU_SINGLE_PROCESS_RENDER"] = "1"
        env["MINERU_PDF_RENDER_THREADS"] = "1"
    return env


def _resolve_mineru_profile(settings: Settings, mineru_mode: str) -> tuple[str, bool, bool]:
    if mineru_mode == "full":
        return "auto", True, True
    if mineru_mode == "math_heavy":
        return "ocr", True, False
    return (
        settings.mineru_method or "txt",
        settings.mineru_formula_enable,
        settings.mineru_table_enable,
    )


def _normalize_mineru_lang(lang: str) -> str:
    aliases = {
        "pt": "latin",
        "pt-pt": "latin",
        "pt_br": "latin",
        "pt-br": "latin",
        "portuguese": "latin",
    }
    normalized = (lang or "").strip().lower()
    return aliases.get(normalized, normalized or "latin")


def _shell_prefix_from_env(env: dict[str, str]) -> str:
    return " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())


def _build_mineru_command(
    settings: Settings,
    pdf_path: Path,
    output_dir: Path,
    start_page: int | None,
    end_page: int | None,
    mineru_mode: str,
) -> str:
    mineru_python = _detect_mineru_python(settings)
    mineru_binary = _detect_mineru_binary(settings)
    if not mineru_python and not mineru_binary:
        return ""

    method, formula_enable, table_enable = _resolve_mineru_profile(settings, mineru_mode)

    parts: list[str] = []
    env_prefix = _shell_prefix_from_env(_build_mineru_env(settings, mineru_mode))
    if env_prefix:
        parts.append(env_prefix)

    if mineru_python:
        parts.extend(
            [
                shlex.quote(mineru_python),
                "-m",
                "exames_pipeline.mineru_runner",
            ]
        )
    else:
        parts.append(shlex.quote(mineru_binary))

    parts.extend(
        [
            "-p",
            shlex.quote(str(pdf_path)),
            "-o",
            shlex.quote(str(output_dir)),
            "-b",
            shlex.quote(settings.mineru_backend or "pipeline"),
            "-m",
            shlex.quote(method),
            "-l",
            shlex.quote(_normalize_mineru_lang(settings.mineru_lang)),
            "-f",
            "true" if formula_enable else "false",
            "-t",
            "true" if table_enable else "false",
        ]
    )

    if start_page is not None:
        parts.extend(["-s", str(start_page)])
    if end_page is not None:
        parts.extend(["-e", str(end_page)])

    return " ".join(parts)


def _resolve_output_dir(settings: Settings, pdf_path: Path, workspace_name: str | None = None) -> Path:
    stem = slugify(workspace_name or pdf_path.stem)
    return ensure_dir(settings.workdir / stem)


def _simulate_extraction(
    pdf_path: Path,
    output_dir: Path,
    parser_stdout: str = "",
    parser_stderr: str = "",
) -> ExtractionResult:
    markdown_path = output_dir / "prova.md"
    images_dir = ensure_dir(output_dir / "imagens_extraidas")
    markdown_path.write_text(
        "\n".join(
            [
                f"# Extração simulada para {pdf_path.name}",
                "",
                "1. [PREENCHER] Questao extraida automaticamente.",
                "",
                "A. Opcao 1",
                "B. Opcao 2",
                "C. Opcao 3",
                "D. Opcao 4",
            ]
        ),
        encoding="utf-8",
    )
    return ExtractionResult(
        pdf_path=pdf_path,
        output_dir=output_dir,
        markdown_path=markdown_path,
        images_dir=images_dir,
        parser_stdout=parser_stdout or "Extração simulada: defina PDF_PARSER_COMMAND para usar um parser real.",
        parser_stderr=parser_stderr,
        simulated=True,
    )


def _extract_markdown_image_names(markdown_text: str) -> list[str]:
    return [Path(image_path).name for _, image_path in MARKDOWN_IMAGE_PATTERN.findall(markdown_text)]


def _find_generated_markdown(output_dir: Path, pdf_path: Path, mineru_mode: str) -> Path | None:
    preferred_dirs = {
        "light": ["txt", "ocr"],
        "full": ["auto", "txt", "ocr"],
        "math_heavy": ["ocr", "auto", "txt"],
    }.get(mineru_mode, ["txt", "ocr", "auto"])

    for dirname in preferred_dirs:
        preferred = output_dir / pdf_path.stem / dirname / f"{pdf_path.stem}.md"
        if preferred.exists():
            return preferred

    candidates = [
        path
        for path in output_dir.rglob("*.md")
        if path.name != "prova.md"
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda path: (path.name != f"{pdf_path.stem}.md", len(path.parts), path.name))
    return candidates[0]


def _find_generated_content_list(output_dir: Path, pdf_path: Path, mineru_mode: str) -> Path | None:
    preferred_dirs = {
        "light": ["txt", "ocr"],
        "full": ["auto", "txt", "ocr"],
        "math_heavy": ["ocr", "auto", "txt"],
    }.get(mineru_mode, ["txt", "ocr", "auto"])

    for dirname in preferred_dirs:
        preferred = output_dir / pdf_path.stem / dirname / f"{pdf_path.stem}_content_list.json"
        if preferred.exists():
            return preferred

    candidates = sorted(output_dir.rglob("*_content_list.json"))
    return candidates[0] if candidates else None


def _find_preprocessed_content_list(output_dir: Path) -> Path | None:
    candidates = sorted(output_dir.rglob("*preprocessed*_content_list.json"))
    return candidates[0] if candidates else None


def _rewrite_markdown_image_paths(markdown_text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        alt_text, image_path = match.groups()
        return f"![{alt_text}](imagens_extraidas/{Path(image_path).name})"

    return MARKDOWN_IMAGE_PATTERN.sub(_replace, markdown_text)


def _bbox_distance(a: list[int] | None, b: list[int] | None) -> int:
    if not a or not b or len(a) != 4 or len(b) != 4:
        return 10**12
    return sum((int(x) - int(y)) ** 2 for x, y in zip(a, b))


def _load_content_list(content_list_path: Path | None) -> list[dict]:
    if content_list_path is None or not content_list_path.exists():
        return []
    try:
        data = json.loads(content_list_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [item for item in data if isinstance(item, dict)]


def _normalize_entry_text(text: str) -> str:
    return text.replace("\u00a0", " ").strip()


def _best_preprocessed_match(entry: dict, preprocessed_entries: list[dict]) -> dict | None:
    if not preprocessed_entries:
        return None
    same_page = [
        candidate for candidate in preprocessed_entries
        if candidate.get("page_idx") == entry.get("page_idx")
    ]
    if not same_page:
        return None

    target_type = entry.get("type")
    preferred = [candidate for candidate in same_page if candidate.get("type") == target_type]
    pool = preferred or same_page
    return min(pool, key=lambda candidate: _bbox_distance(entry.get("bbox"), candidate.get("bbox")))


def _content_item_to_markdown(entry: dict, preprocessed_entries: list[dict]) -> str:
    entry_type = entry.get("type")
    matched = _best_preprocessed_match(entry, preprocessed_entries)

    if entry_type in {"text", "title"}:
        text = _normalize_entry_text((matched or entry).get("text", ""))
        if not text:
            return ""
        text_level = entry.get("text_level") or (matched or {}).get("text_level")
        if text_level and not text.startswith("#"):
            heading_level = max(1, min(int(text_level), 4))
            return f"{'#' * heading_level} {text}"
        return text

    if entry_type == "equation":
        latex_text = _normalize_entry_text((matched or {}).get("text", "") or entry.get("text", ""))
        if latex_text:
            return latex_text
        img_name = Path(entry.get("img_path", "")).name
        return f"![](imagens_extraidas/{img_name})" if img_name else ""

    if entry_type in {"image", "table"}:
        img_name = Path(entry.get("img_path", "")).name
        return f"![](imagens_extraidas/{img_name})" if img_name else ""

    return ""


def _build_markdown_from_content_list(
    content_entries: list[dict],
    preprocessed_entries: list[dict],
) -> str:
    blocks: list[str] = []
    for entry in content_entries:
        block = _content_item_to_markdown(entry, preprocessed_entries)
        if not block:
            continue
        if blocks and blocks[-1] == block:
            continue
        blocks.append(block)
    return "\n\n".join(blocks).strip()


def _normalize_latex_atom(value: str) -> str:
    compact = " ".join(value.split())
    if compact.replace(" ", "").isdigit():
        return compact.replace(" ", "")
    return compact


def _normalize_latex_math(markdown_text: str) -> str:
    def _replace_frac(match: re.Match[str]) -> str:
        numerator = _normalize_latex_atom(match.group(1))
        denominator = _normalize_latex_atom(match.group(2))
        return f"\\frac{{{numerator}}}{{{denominator}}}"

    def _replace_sup(match: re.Match[str]) -> str:
        base = match.group("base")
        exponent = _normalize_latex_atom(match.group("exp"))
        return f"{base}^{{{exponent}}}"

    def _replace_sub(match: re.Match[str]) -> str:
        base = match.group("base")
        subscript = _normalize_latex_atom(match.group("sub"))
        return f"{base}_{{{subscript}}}"

    normalized = LATEX_FRAC_PATTERN.sub(_replace_frac, markdown_text)
    normalized = LATEX_SUP_PATTERN.sub(_replace_sup, normalized)
    normalized = LATEX_SUB_PATTERN.sub(_replace_sub, normalized)
    normalized = LATEX_CMD_SPACE_PATTERN.sub(r"\\\g<cmd>{", normalized)

    replacements = {
        "\\times { }": "\\times ",
        "{ } \\times": " \\times",
        "\\times^": "\\times ^",
        "\\times ^ {": "\\times ^{",
        "{ } ^": "^",
        "{ } _": "_",
        "\\mathrm { ": "\\mathrm{",
        "\\mathbb { ": "\\mathbb{",
        "\\mathbf { ": "\\mathbf{",
        "\\boldsymbol { ": "\\boldsymbol{",
        "\\displaystyle { ": "\\displaystyle{",
        "\\bigl (": "\\bigl(",
        "\\bigr )": "\\bigr)",
        "{ \\bigl(": "\\bigl(",
        "\\bigl( }": "\\bigl(",
        "{ \\bigr)": "\\bigr)",
        "\\bigr) }": "\\bigr)",
        "\\left\\{ \\begin{array}": "\\left\\{\\begin{array}",
        "\\qquad }": "\\qquad}",
        "{ \\left\\{": "\\left\\{",
        "\\mathrm{ s e n }": "\\sin",
        "\\mathrm{ c o s }": "\\cos",
        "\\mathrm{ t a n }": "\\tan",
    }
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)

    normalized = LATEX_FUNC_JOIN_PATTERN.sub(r"\\\g<func> \g<arg>", normalized)
    normalized = LATEX_COMBINATORICS_PATTERN.sub(r"^{\g<sup>} \g<sym>_{\g<sub>}", normalized)
    normalized = re.sub(r"\{\s*\}", "", normalized)
    normalized = re.sub(r" +", " ", normalized)

    # Fix MinerU artefacts in array environments:
    # \begin{array} { l l } → \begin{array}{ll}  (extra braces + spaces in column spec)
    def _fix_array_colspec(m: re.Match) -> str:
        return r"\begin{array}{" + m.group(1).replace(" ", "") + "}"
    normalized = re.sub(r"\\begin\{array\}\s*\{([^}]*)\}", _fix_array_colspec, normalized)

    # Fix spaced letters inside \mathrm{}: \mathrm{ s e } → \text{se}
    normalized = re.sub(
        r"\\mathrm\{\s*([A-Za-z](?:\s+[A-Za-z])*)\s*\}",
        lambda m: r"\text{" + m.group(1).replace(" ", "") + "}",
        normalized,
    )

    # Remove spurious trailing } after \right. at end of a $$ block:
    # "... \end{array} \right. }\n$$" → "... \end{array} \right.\n$$"
    normalized = re.sub(r"(\\right\.)\s*\}(\s*\n\$\$)", r"\1\2", normalized)

    return normalized


def _normalize_question_markers(markdown_text: str) -> str:
    """Remove prefixos de asterisco/estrela dos cabeçalhos de questões.

    Os exames nacionais usam ★ / * como marcadores visuais antes do número de
    alguns itens (itens opcionais ou de grupo diferente). O MinerU converte esses
    símbolos para LaTeX inline ($\\star$, $\\bigstar$, $\\ast$) ou asterisco markdown
    (\\*), o que impede o segmentador de reconhecer o número da questão.

    Casos tratados:
      $\\star \\ 1 .$   → 1.    (número dentro do LaTeX com espaços)
      $\\star$ 8.        → 8.    (estrela antes do número)
      $\\bigstar$ 5.1.   → 5.1.  (estrela grande antes do número)
      $\\ast$ 5.2.       → 5.2.  (asterisco LaTeX antes do número)
      \\*2.2.            → 2.2.  (asterisco markdown antes do número)

    Limitação: quando o OCR leu o número com erros dentro do bloco LaTeX
    (ex: "10" confundido com "1") não há forma de recuperar o número correto.
    """
    # Caso 1: número DENTRO do bloco LaTeX — "$\star \ N .$" ou "$\bigstar N.N.$"
    # O número pode ter espaços entre dígitos e entre o número e o ponto final.
    normalized = re.sub(
        r"\$\\(?:star|bigstar|ast)\b(?:[^$\d]*?)(\d+(?:[\s.]\d+)*)\s*\.\s*\$\s*",
        lambda m: re.sub(r"\s+", "", m.group(1)) + ". ",
        markdown_text,
    )

    # Caso 2: estrela LaTeX ANTES do número (separados) — "$\star$ 8." ou "$\bigstar$ 5.1."
    normalized = re.sub(
        r"\$\\(?:star|bigstar|ast)\$\s*(\d+(?:\.\d+)*\.?)\s*",
        lambda m: m.group(1) + " ",
        normalized,
    )

    # Caso 3: asterisco markdown antes do número — "\*2.2." ou "\*3.2."
    normalized = re.sub(
        r"\\\*(\d+(?:\.\d+)*\.?)",
        lambda m: m.group(1),
        normalized,
    )

    # Caso 4: bloco LaTeX composto com estrela antes do número — "$\big \langle \star$ 4.1."
    # Generaliza Caso 2 para padrões como $\big \langle \star$, $\langle \star$ etc.
    normalized = re.sub(
        r"\$[^$\d]*\\(?:star|bigstar|ast)\b[^$\d]*\$\s*(\d+(?:\.\d+)*\.?)\s*",
        lambda m: m.group(1) + " ",
        normalized,
    )

    # Caso D1: ponto de questão colado a texto — "5.Um" → "5. Um"
    # Ocorre quando o OCR omite o espaço após o ponto separador.
    normalized = re.sub(
        r"(?m)^(\d{1,2}\.)([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])",
        r"\1 \2",
        normalized,
    )

    # Caso D2: ponto de subitem colado a texto — "3.2.Considere" → "3.2. Considere"
    # Igual ao D1 mas para subitens com dois níveis (X.Y.Texto).
    normalized = re.sub(
        r"(?m)^(\d{1,2}\.\d{1,2}\.)([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])",
        r"\1 \2",
        normalized,
    )

    # Caso B1: número no início de linha com espaço mas sem ponto — "4 Sendo" → "4. Sendo"
    # Ocorre quando o OCR lê o número correto mas omite o ponto separador da questão.
    normalized = re.sub(
        r"(?m)^(\d{1,2}) (?=[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])",
        r"\1. ",
        normalized,
    )

    # Caso C1: subitem colapsado — "42." → "4.2."
    # O OCR funde o ponto separador do subitem com os dígitos adjacentes.
    # Condições para converter "XY." → "X.Y." no início de linha:
    #   1. X é item principal reconhecido no documento
    #   2. X.1. existe (confirma que X tem subitens)
    #   3. XY não é item principal reconhecido (evita converter "12." quando item 12 existe)
    # Padrão para prefixo "\* " no início de linha (barra invertida + asterisco + espaço).
    # Em Python regex, \* é quantificador; para literais usar \\[*] ou \\\\\* (4 barras).
    _STAR_PREFIX = r"^(?:\\[*] )?"

    # Caso C1 — duas passagens para evitar circularidade:
    #   1.ª passagem: recolher sub_items (padrão X.Y.) e derivar os pais com subitens
    #   2.ª passagem: corrigir "XY." → "X.Y." quando X tem subitens confirmados
    lines = normalized.split("\n")
    sub_items: set[str] = set()
    for line in lines:
        m = re.match(_STAR_PREFIX + r"(\d{1,2}\.\d+)\. ", line)
        if m:
            sub_items.add(m.group(1))
    # parent_items: itens que têm pelo menos um subitem reconhecido
    parent_items = {s.split(".")[0] for s in sub_items}
    fixed_lines = []
    for line in lines:
        m = re.match(r"^(\d)([1-9])\. ", line)
        if m:
            x, y = m.group(1), m.group(2)
            prev_sub = f"{x}.{int(y) - 1}" if int(y) > 1 else None
            has_context = (prev_sub and prev_sub in sub_items) or f"{x}.1" in sub_items
            if x in parent_items and has_context:
                line = f"{x}.{y}. " + line[4:]  # line[4:] salta "XY. " (4 chars)
        fixed_lines.append(line)
    normalized = "\n".join(fixed_lines)

    # Reconstruir main_items após a correção C1 (para o Caso A2 usar valores limpos)
    lines = normalized.split("\n")
    main_items: set[str] = set()
    for line in lines:
        m = re.match(_STAR_PREFIX + r"(\d{1,2})\. ", line)
        if m:
            main_items.add(m.group(1))

    # Caso A2: "\* " sem número — inferir número pelo contexto.
    # O OCR reconhece a estrela mas perde o número da questão (e eventualmente
    # a palavra inicial). Estratégia: se o próximo item numerado é N, este é N-1.
    # Ex: "\* $\left( 1+..." seguido de "2. A Figura..." → "\* 1. $\left(..."
    fixed_lines = []
    for i, line in enumerate(lines):
        if re.match(r"^\\[*] (?!\d)", line):
            for j in range(i + 1, len(lines)):
                m = re.match(_STAR_PREFIX + r"(\d{1,2})\. ", lines[j])
                if m:
                    next_n = int(m.group(1))
                    if next_n > 1:
                        line = r"\* " + f"{next_n - 1}. " + line[3:]
                    break
        fixed_lines.append(line)
    normalized = "\n".join(fixed_lines)

    return normalized


_MATH_BLOCK_SPLIT_RE = re.compile(r"(\$\$[^$]*?\$\$|\$[^$\n]+?\$)", re.DOTALL)


def _apply_outside_math(text: str, pattern: re.Pattern, repl: str) -> str:
    """Aplica substituição apenas nos segmentos fora de blocos $...$ e $$...$$."""
    parts = _MATH_BLOCK_SPLIT_RE.split(text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 0:  # segmento fora de math — aplicar substituição
            result.append(pattern.sub(repl, part))
        else:  # bloco math — não tocar
            result.append(part)
    return "".join(result)


# \in fora de math: antes de artigo/determinante → "é", caso contrário → "e"
_IN_BEFORE_ARTIGO_RE = re.compile(r"\\in\s+(?=um[a]?\b|o\b|os\b|a\b|as\b)")
_IN_DEFAULT_RE = re.compile(r"\\in\b")


def _normalize_text_artifacts(markdown_text: str) -> str:
    replacements = {
        "I, I, II e IV": "I, II, III e IV",
        "Il valores": "II valores",
        "menordesses": "menor desses",
        "coma horizontal": "com a horizontal",
        "a), )ou c)": "a), b) ou c)",
        ")ou c)": ") ou c)",
        "A3×3×5!": "A_{3} \\times 3! \\times 5!",
        "C 3 ! ! 4 3 # #": "^{4}C_{3} \\times 3! \\times 5!",
        "2 \\times ^{ 4 } A_{3}": "2 \\times ^{4} A_{3}",
        "2 \\times ^{ 4 } C_{3}": "2 \\times ^{4} C_{3}",
    }
    normalized = markdown_text
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)

    # Corrigir \in fora de blocos matemáticos (OCR confunde "e"/"é" com ∈)
    # Pass 1: \in antes de artigo/determinante → "é" (é uma, é o, é a, ...)
    normalized = _apply_outside_math(normalized, _IN_BEFORE_ARTIGO_RE, "é ")
    # Pass 2: restantes \in → "e" (conjunção)
    normalized = _apply_outside_math(normalized, _IN_DEFAULT_RE, "e")

    # Corrigir formatação de pontos de tópico (•)
    # Pass 1: garantir newline antes de bullet inline (precedido de não-espaço)
    normalized = re.sub(r"(\S)[ \t]*•", r"\1\n•", normalized)
    # Pass 2: garantir espaço após bullet
    normalized = re.sub(r"•(?=[^\s])", "• ", normalized)

    # Limpeza: remover espaços/tabs em branco no fim de linha (artefacto MinerU)
    # "candidatos eram violinistas; \n" → "candidatos eram violinistas;\n"
    normalized = re.sub(r"[^\S\n]+\n", "\n", normalized)

    # Regra de quebra de linha 1: inserir \n após ponto/ponto-e-vírgula antes de
    # verbos de instrução, quando OCR os fundiu na mesma linha.
    # "flautistas. Seleciona-se" → "flautistas.\nSeleciona-se"
    # Aplica apenas fora de blocos matemáticos e só quando não há já um \n.
    _INSTR_VERB_AFTER_SEP_RE = re.compile(
        # (?<!\d) evita match no ponto de cabeçalhos numerados ("3.2. Determine")
        r"(?<!\d)([.;])[^\S\n]+"
        r"(Determine\b|Mostre\b|Apresente\b|Resolva\b|Calcule\b|"
        r"Justifique\b|Escreva\b|Represente\b|Assinale\b|"
        r"Seleciona-se\b|Considera-se\b|Admita-se\b|Observe-se\b|"
        r"Na\s+sua\s+resposta\b)"
    )
    normalized = _apply_outside_math(normalized, _INSTR_VERB_AFTER_SEP_RE, r"\1\n\2")

    # Regra de quebra de linha 2: promover \n simples para \n\n antes de verbos
    # de instrução que sempre iniciam um novo parágrafo lógico.
    # "...os pontos B e C pertencem...\nMostre que" → "...\n\nMostre que"
    # Não afeta sequências já com \n\n (lookbehind impede segundo match).
    _STRONG_INSTR_UPGRADE_RE = re.compile(
        r"(?<!\n)\n"
        r"(Determine\b|Mostre\b|Apresente\b|Resolva\b|Calcule\b|"
        r"Justifique\b|Seleciona-se\b|Considera-se\b)"
    )
    normalized = _apply_outside_math(normalized, _STRONG_INSTR_UPGRADE_RE, r"\n\n\1")

    return normalized


def _strip_formulario_section(markdown_text: str) -> str:
    """Remove a secção de formulário do markdown extraído pelo MinerU.

    Detecta o título da página (FORMULÁRIO, FORMULÁRIOS, F O R M U L Á R I O, etc.)
    e remove tudo desde esse cabeçalho até ao início da secção seguinte (próximo
    cabeçalho markdown). Se não existir secção seguinte, não remove nada — evitar
    apagar conteúdo útil em documentos com estrutura inesperada.
    """
    m = _FORMULARIO_HEADING_RE.search(markdown_text)
    if not m:
        return markdown_text

    # Recuar o ponto de corte para absorver linhas em branco antes do cabeçalho
    pre = markdown_text[: m.start()].rstrip("\n")
    form_start = len(pre) + 1 if pre else 0

    # Encontrar o próximo cabeçalho após o formulário
    next_heading = _NEXT_HEADING_RE.search(markdown_text, m.end())
    if not next_heading:
        print("[pdf_parser] ⚠️  Formulário detectado mas sem secção seguinte — a manter.")
        return markdown_text

    form_end = next_heading.start()
    removed_chars = form_end - form_start
    result = markdown_text[:form_start].rstrip("\n") + "\n\n" + markdown_text[form_end:].lstrip("\n")
    print(f"[pdf_parser] ✂️  Secção de formulário removida ({removed_chars} caracteres).")
    return result.strip()


def _normalize_mineru_output(
    output_dir: Path,
    pdf_path: Path,
    markdown_path: Path,
    images_dir: Path,
    mineru_mode: str,
) -> None:
    generated_markdown = _find_generated_markdown(output_dir, pdf_path, mineru_mode)
    generated_content_list = _find_generated_content_list(output_dir, pdf_path, mineru_mode)
    preprocessed_content_list = _find_preprocessed_content_list(output_dir)
    if generated_markdown is None:
        markdown_path.write_text("", encoding="utf-8")
        return

    content_entries = _load_content_list(generated_content_list)
    preprocessed_entries = _load_content_list(preprocessed_content_list)

    markdown_text = ""
    if content_entries:
        markdown_text = _build_markdown_from_content_list(content_entries, preprocessed_entries)
    if not markdown_text:
        markdown_text = generated_markdown.read_text(encoding="utf-8")

    markdown_text = _normalize_latex_math(markdown_text)
    markdown_text = _normalize_question_markers(markdown_text)
    markdown_text = _normalize_text_artifacts(markdown_text)
    markdown_text = _strip_formulario_section(markdown_text)
    markdown_path.write_text(_rewrite_markdown_image_paths(markdown_text), encoding="utf-8")

    referenced_image_names = set(_extract_markdown_image_names(markdown_text))
    source_root = generated_markdown.parent
    image_candidates = {
        image_file.name: image_file
        for image_file in source_root.rglob("*")
        if image_file.is_file() and image_file.suffix.lower() in IMAGE_EXTENSIONS
    }
    for image_name in sorted(referenced_image_names):
        image_file = image_candidates.get(image_name)
        if image_file is None:
            continue
        destination = images_dir / image_file.name
        if image_file.resolve() == destination.resolve():
            continue
        shutil.copyfile(image_file, destination)


def _has_normalized_output(markdown_path: Path, images_dir: Path) -> bool:
    if markdown_path.exists() and markdown_path.stat().st_size > 0:
        return True
    return any(images_dir.iterdir())


def extract_pdf(
    settings: Settings,
    pdf_path: Path,
    workspace_name: str | None = None,
    start_page: int | None = None,
    end_page: int | None = None,
    mineru_mode: str | None = None,
    preprocess: bool = True,
) -> ExtractionResult:
    pdf_path = pdf_path.resolve()
    output_dir = _resolve_output_dir(settings, pdf_path, workspace_name=workspace_name)
    images_dir = ensure_dir(output_dir / "imagens_extraidas")
    markdown_path = output_dir / "prova.md"
    resolved_mineru_mode = _resolve_mineru_mode(settings, mineru_mode)

    # Módulo 0.5: pré-processar o PDF antes do MinerU para melhorar OCR
    if preprocess:
        from .module_preprocess import preprocess_pdf_for_ocr  # noqa: PLC0415
        pdf_for_ocr = preprocess_pdf_for_ocr(pdf_path, output_dir)
    else:
        pdf_for_ocr = pdf_path

    command = settings.pdf_parser_command
    if not command and settings.pdf_parser_backend.lower() == "mineru":
        command = _build_mineru_command(
            settings,
            pdf_for_ocr,           # PDF pré-processado (ou original se falhou)
            output_dir,
            start_page=start_page,
            end_page=end_page,
            mineru_mode=resolved_mineru_mode,
        )

    if not command:
        return _simulate_extraction(pdf_path, output_dir)

    command = command.format(
        input=str(pdf_for_ocr),
        output=str(output_dir),
        images=str(images_dir),
        markdown=str(markdown_path),
        backend=settings.mineru_backend,
        lang=settings.mineru_lang,
    )
    completed = run_command(command, cwd=settings.project_root)

    if completed.returncode != 0:
        return _simulate_extraction(
            pdf_path,
            output_dir,
            parser_stdout=completed.stdout,
            parser_stderr=completed.stderr,
        )

    _normalize_mineru_output(output_dir, pdf_path, markdown_path, images_dir, resolved_mineru_mode)
    if not _has_normalized_output(markdown_path, images_dir):
        return _simulate_extraction(
            pdf_path,
            output_dir,
            parser_stdout=completed.stdout,
            parser_stderr=completed.stderr or "MinerU terminou sem gerar markdown ou imagens normalizadas.",
        )

    return ExtractionResult(
        pdf_path=pdf_path,
        output_dir=output_dir,
        markdown_path=markdown_path,
        images_dir=images_dir,
        parser_stdout=completed.stdout,
        parser_stderr=completed.stderr,
        simulated=False,
    )
