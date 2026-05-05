from __future__ import annotations

from pathlib import Path
import re

from .schemas import EstruturaCotacoes, Question, dump_json, dump_questions, load_cotacoes, load_json, load_questions


# Suporta: "1", "2.1", "I-1", "II-2.1", "I-ctx1", "I-ctx2", "II-ctx1"
# ctx\d* cobre tanto o legado "I-A-ctx" (ctx sem número) como o novo "I-ctx1"
ITEM_ID_PATTERN = re.compile(
    r"^(?:(?P<grupo>[IVX]+)-)?(?:(?P<parte>[A-C])-)?(?P<main>\d{1,3}|ctx\d*)(?:\.(?P<sub>\d{1,2}))?$"
)
MISSING_CREDENTIALS_NOTE_PATTERN = re.compile(r"^Fornecedor '.+' sem credenciais;")
MIN_TEXT_LENGTH = 30

# --- Módulo 3: novos limiares e padrões ---
MAX_ALTERNATIVE_TEXT_CHARS = 400
WARN_ALTERNATIVE_TEXT_CHARS = 200
TASK_VERB_IN_ALTERNATIVE_PATTERN = re.compile(
    r"\b(Determine|Calcule|Resolva|Mostre|Escreva|Apresente|Justifique|Averigue|Estude|Indique"
    r"|Complete|Represente|Prove|Classifique|Obtenha|Simplifique)\b",
    re.IGNORECASE,
)
METADATA_CONTAMINATION_PATTERN = re.compile(
    r"(?m)(?:^#\s*COTA[ÇC][ÕO]ES\b|^\s*GRUPO\s+[IV\d]|\bPág\.\s*\d+|\bVers[aã]o\s+\d)",
    re.IGNORECASE,
)
# Detecção de artefactos OCR no enunciado
FUSED_NUMBER_PREFIX_PATTERN = re.compile(
    r"^\d{1,3}[A-ZÁÉÍÓÚÀÂÃÇ]"   # "1Na Figura..."
    r"|^\$\\pm\s*\d"              # "$\pm 8 .$"
    r"|^\$\\pm\s*\$\s*\d"         # variantes OCR
)

# Correcções determinísticas (sem IA) aplicadas antes da validação
# Cada entrada: (padrão de detecção, substituição, descrição)
# IMPORTANTE: a ordem importa — padrões LaTeX vêm primeiro para que os padrões
# numéricos seguintes possam apanhar os resíduos (ex: "$\pm 8.$" → "8." → "")
_DETERMINISTIC_FIXES: list[tuple[re.Pattern, str, str]] = [
    # "$\\pm 6 . 1 .$" → ""  (remove prefixo LaTeX \pm de subitem)
    (
        re.compile(r"^\$\\pm\s*(\d{1,3})\s*\.\s*(\d{1,2})\s*\.\s*\$\s*"),
        r"",
        "prefixo LaTeX \\pm fundido a subitem (artefacto OCR)",
    ),
    # "$\\pm 8 .$" → ""  (remove prefixo LaTeX \pm de item — inclui resíduo após \pm)
    (
        re.compile(r"^\$\\pm\s*(\d{1,3})\s*\.\s*\$\s*"),
        r"",
        "prefixo LaTeX \\pm fundido a item (artefacto OCR)",
    ),
    # "$\\ast$ 3. Numa" → "Numa"  |  "$\\bigstar$ 1.1. Qual" → "Qual"
    (
        re.compile(r"^\$\\(?:ast|bigstar|star|bullet|cdot)\$\s*\d{1,3}(?:\.\d{1,2})*\.?\s*"),
        r"",
        "prefixo LaTeX decorativo + número do item no início do enunciado",
    ),
    # "10.2. Estude" → "Estude"  |  "1.1. Qual" → "Qual"  |  "10.2.Estude" → "Estude"
    (
        re.compile(r"^\d{1,3}\.\d{1,2}\.\s*"),
        r"",
        "prefixo de subitem no início do enunciado",
    ),
    # "2. Na Figura" → "Na Figura"  |  "15. Considere" → "Considere"  |  "8.Em" → "Em"
    (
        re.compile(r"^\d{1,3}\.\s*"),
        r"",
        "prefixo numérico do item no início do enunciado",
    ),
    # "1Na Figura" → "Na Figura"  |  "3Qual" → "Qual"
    (
        re.compile(r"^(\d{1,3})([A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇÈÌÒÙ])"),
        r"\2",
        "prefixo numérico fundido ao texto (artefacto OCR)",
    ),
]
STEM_TASK_VERB_PATTERN = re.compile(
    r"\b(Determine|Calcule|Resolva|Mostre|Escreva|Apresente|Justifique|Averigue|Estude|Indique"
    r"|Complete|Represente|Prove|Classifique|Obtenha|Simplifique)\b",
    re.IGNORECASE,
)
SUBITEM_REFERENCE_PATTERN = re.compile(r"\b(\d{1,3})\.(\d{1,2})\.")

# Deteção de LaTeX fora de ambiente matemático ($...$)
# Cobre: \command, A_{, x^{, ^{n}, _{n}
_MATH_BLOCK_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+?\$", re.DOTALL)
_LATEX_OUTSIDE_MATH_RE = re.compile(
    r"\\[a-zA-Z]+"           # \times, \frac, \sqrt, \cdot, ...
    r"|[A-Za-z]\s*_\s*\{"   # A_{, x_{, C_{
    r"|[A-Za-z]\s*\^\s*\{"  # A^{, x^{
    r"|\d+\s*_\s*\{"        # 4_{
    r"|\^\s*\{"             # ^{  (sozinho)
)
_ALT_MARKER_PREFIX_RE = re.compile(r"^\(([A-D])\)\s*")
_ALTERNATIVES_IN_ENUNCIADO_PATTERN = re.compile(r"(?:^|\n)\s*\(A\)[\s\S]*$")


def _text_outside_math(text: str) -> str:
    """Retorna o texto com os blocos $...$ e $$...$$ removidos — só o texto fora de math."""
    return _MATH_BLOCK_RE.sub("", text)


def _fix_undelimited_math(text: str) -> tuple[str, str | None]:
    """Se o texto não contém $ mas tem LaTeX, envolve-o em $...$. Retorna (texto, descrição|None)."""
    stripped = text.strip()
    if "$" in stripped:
        return text, None  # já tem delimitadores, não tocar
    if _LATEX_OUTSIDE_MATH_RE.search(stripped):
        return f"${stripped}$", "LaTeX fora de ambiente matemático: envolvido em $...$"
    return text, None


def _apply_deterministic_fixes(question: Question) -> list[str]:
    """Aplica correcções determinísticas (sem IA) ao enunciado e alternativas.

    Corrige artefactos OCR simples que podem ser resolvidos com regex:
    prefixos numéricos fundidos ao texto, artefactos LaTeX \\pm, etc.

    Retorna lista de correcções aplicadas (strings descritivas) para log.
    """
    applied: list[str] = []

    def _fix_text(text: str) -> tuple[str, list[str]]:
        fixes: list[str] = []
        stripped = text.lstrip()
        for pattern, replacement, description in _DETERMINISTIC_FIXES:
            fixed = pattern.sub(replacement, stripped)
            if fixed != stripped:
                fixes.append(description)
                stripped = fixed
        # Reconstituir leading whitespace se existia
        lead = text[: len(text) - len(text.lstrip())]
        return lead + stripped, fixes

    # Corrigir enunciado
    if question.enunciado:
        fixed, fixes = _fix_text(question.enunciado)
        if fixes:
            question.enunciado = fixed
            applied.extend(fixes)

    # Corrigir texto das alternativas
    for alt in question.alternativas or []:
        if hasattr(alt, "texto") and alt.texto:
            fixed, fixes = _fix_text(alt.texto)
            if fixes:
                alt.texto = fixed
                applied.extend([f"alternativa {alt.letra}: {f}" for f in fixes])
            # Corrigir LaTeX sem delimitadores $
            math_fixed, math_desc = _fix_undelimited_math(alt.texto)
            if math_desc:
                alt.texto = math_fixed
                applied.append(f"alternativa {alt.letra}: {math_desc}")

    return applied


def _item_sort_key(question: Question) -> tuple[int, int, int]:
    order = question.ordem_item or question.numero_questao
    main_number = question.numero_principal or question.numero_questao
    subitem = int(question.subitem) if question.subitem and question.subitem.isdigit() else 0
    return (order, main_number, subitem)


def _trace_key(question: Question) -> tuple[str, int]:
    return (question.id_item or "", question.ordem_item or question.numero_questao)


def _load_trace_map(raw_json_path: Path) -> dict[tuple[str, int], dict]:
    traces_path = raw_json_path.with_suffix(".traces.json")
    if not traces_path.exists():
        return {}
    raw = load_json(traces_path)
    trace_map: dict[tuple[str, int], dict] = {}
    for trace in raw:
        if not isinstance(trace, dict):
            continue
        try:
            order_value = int(trace.get("ordem_item") or trace.get("numero_questao") or 0)
        except (TypeError, ValueError):
            continue
        key = (str(trace.get("id_item", "")).strip(), order_value)
        if order_value <= 0:
            continue
        trace_map[key] = trace
    return trace_map


def _validate_alternatives(question: Question) -> list[str]:
    errors: list[str] = []
    alternatives = question.alternativas or []
    if question.tipo_item == "multiple_choice":
        if len(alternatives) != 4:
            errors.append(f"Esperadas 4 alternativas, encontradas {len(alternatives)}.")
            return errors
        letters = [alt.letra.strip().upper() for alt in alternatives]
        if letters != ["A", "B", "C", "D"]:
            errors.append(f"Letras de alternativas inválidas: {letters}.")
        for alt in alternatives:
            normalized_text = alt.texto.strip()
            if not normalized_text:
                errors.append(f"Alternativa {alt.letra} vazia.")
                continue
            # Aceitar constantes matemáticas LaTeX curtas: $e$, $i$, $\pi$, $\infty$, etc.
            is_latex_constant = bool(re.match(r"^\$[^$]{1,10}\$$", normalized_text))
            if len(normalized_text) < 2 and not re.search(r"\d", normalized_text) and not is_latex_constant:
                errors.append(f"Alternativa {alt.letra} com texto demasiado curto.")
    elif question.tipo_item in ("essay", "open_response", "complete_table", "multi_select"):
        pass  # tipos PT sem alternativas — esperado
    elif alternatives and len(alternatives) not in {0, 4}:
        errors.append(
            f"Questao do tipo '{question.tipo_item}' com alternativas incompletas: {len(alternatives)}."
        )
    elif question.tipo_item != "multiple_choice" and len(alternatives) == 4:
        errors.append(
            f"Questao do tipo '{question.tipo_item}' tem 4 alternativas, sugerindo tipo incorreto."
        )
    return errors


def _validate_item_identity(question: Question) -> list[str]:
    errors: list[str] = []
    if not question.id_item:
        errors.append("Campo id_item ausente.")
        return errors
    match = ITEM_ID_PATTERN.match(question.id_item.strip())
    if not match:
        errors.append(f"Formato invalido de id_item: '{question.id_item}'.")
        return errors
    main_from_id = int(match.group("main"))
    sub_from_id = match.group("sub")
    grupo_from_id = match.group("grupo")
    # Quando o id_item tem prefixo de grupo (ex: "II-1"), o numero_principal/numero_questao
    # pode conter o número global (ex: 9) — não verificar consistência numérica nesses casos.
    if not grupo_from_id:
        if question.numero_principal is not None and question.numero_principal != main_from_id:
            errors.append(
                f"numero_principal ({question.numero_principal}) inconsistente com id_item ({question.id_item})."
            )
        if question.numero_questao != main_from_id:
            errors.append(
                f"numero_questao ({question.numero_questao}) inconsistente com id_item ({question.id_item})."
            )
    if sub_from_id is None and question.subitem is not None:
        errors.append(f"subitem '{question.subitem}' presente num item principal ({question.id_item}).")
    if sub_from_id is not None and question.subitem != sub_from_id:
        errors.append(f"subitem '{question.subitem}' inconsistente com id_item ({question.id_item}).")
    return errors


def _validate_source_span(question: Question) -> list[str]:
    errors: list[str] = []
    if not question.source_span:
        errors.append("Campo source_span ausente.")
        return errors
    line_start = question.source_span.get("line_start")
    line_end = question.source_span.get("line_end")
    if not isinstance(line_start, int) or not isinstance(line_end, int):
        errors.append("source_span inválido: line_start/line_end devem ser inteiros.")
        return errors
    if line_start <= 0 or line_end <= 0 or line_end < line_start:
        errors.append(f"source_span inválido: line_start={line_start}, line_end={line_end}.")
    return errors


def _validate_text_fields(question: Question) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not question.enunciado.strip():
        errors.append("Campo enunciado ausente.")
    compact_enunciado = re.sub(r"\s+", "", question.enunciado or "")
    compact_original = re.sub(r"\s+", "", question.texto_original or "")
    if not compact_original:
        errors.append("Campo texto_original ausente.")
    if compact_enunciado and len(compact_enunciado) < MIN_TEXT_LENGTH:
        warnings.append(f"Enunciado muito curto ({len(compact_enunciado)} caracteres sem espaços).")
    if not (question.fonte or "").strip():
        warnings.append("Campo 'fonte' vazio: use --fonte ou verifique o nome do ficheiro.")
    return errors, warnings


_FIGURA_REFERENCE_PATTERN = re.compile(
    r"\bFigura\s+\d+\b",
    re.IGNORECASE,
)
_INLINE_IMAGE_PATTERN = re.compile(r"!\[.*?\]\(")


def _validate_images(question: Question, images_root: Path) -> list[str]:
    errors: list[str] = []
    for image in question.imagens_contexto or question.imagens:
        image_path = (images_root / image).resolve()
        if not image_path.exists():
            errors.append(f"Imagem ausente: {image}.")
    return errors


def _validate_figura_reference(question: Question) -> list[str]:
    """Erro obrigatório quando o enunciado menciona 'Figura X' mas não há imagem associada.

    Cobre dois casos:
    - q.imagens vazio E sem markdown ![]() no enunciado
    - Contexto do pai (enunciado_contexto_pai) também não tem imagem inline
      (para subitems, a figura está normalmente no pai — verificar q.imagens do grupo
      não é possível aqui sem carregar o grupo completo, por isso verifica-se o campo
      enunciado_contexto_pai como proxy)
    """
    errors: list[str] = []
    combined = (question.enunciado or "") + " " + (question.texto_original or "")
    if not _FIGURA_REFERENCE_PATTERN.search(combined):
        return errors

    has_image = bool(question.imagens) or bool(_INLINE_IMAGE_PATTERN.search(question.enunciado or ""))
    # Para subitems: a figura pode estar no enunciado_contexto_pai
    if not has_image and question.enunciado_contexto_pai:
        has_image = bool(_INLINE_IMAGE_PATTERN.search(question.enunciado_contexto_pai))

    if not has_image:
        refs = _FIGURA_REFERENCE_PATTERN.findall(combined)
        unique_refs = ", ".join(dict.fromkeys(refs))
        errors.append(
            f"Enunciado menciona {unique_refs} mas nenhuma imagem está associada ao item "
            "(q.imagens vazio e sem ![]() no enunciado): imagem provavelmente perdida no OCR."
        )
    return errors


def _validate_trace_signals(trace: dict | None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not trace:
        return errors, warnings
    if trace.get("suspected_numbering_reset"):
        warnings.append("Traço indica reset suspeito de numeração OCR.")
    if trace.get("inferred_from_implicit_boundary"):
        score = trace.get("implicit_boundary_score")
        if isinstance(score, int) and score <= 2:
            errors.append(f"Fronteira implicita inferida com confiança baixa (score={score}).")
        else:
            warnings.append(
                "Traço indica fronteira implícita inferida; validar se o item não mistura enunciados."
            )
    return errors, warnings


def _is_ignorable_observation(note: str) -> bool:
    return bool(MISSING_CREDENTIALS_NOTE_PATTERN.match(note.strip()))


def _append_validation_notes(question: Question, errors: list[str], warnings: list[str]) -> None:
    for error in errors:
        note = f"[validate][erro] {error}"
        if note not in question.observacoes:
            question.observacoes.append(note)
    for warning in warnings:
        note = f"[validate][aviso] {warning}"
        if note not in question.observacoes:
            question.observacoes.append(note)


def _validate_alternative_content(question: Question) -> tuple[list[str], list[str]]:
    """Detecta alternativas com texto excessivamente longo ou com verbos de tarefa.

    Alternativas longas com verbo imperativo são sinal de que outro item foi absorvido
    na última alternativa (problema comum quando o MinerU não separa fronteiras MCQ/discursivo).
    """
    errors: list[str] = []
    warnings: list[str] = []
    if question.tipo_item != "multiple_choice":
        return errors, warnings
    for alt in question.alternativas or []:
        text = alt.texto.strip()
        char_count = len(text)
        if char_count > MAX_ALTERNATIVE_TEXT_CHARS:
            errors.append(
                f"Alternativa {alt.letra} excessivamente longa ({char_count} chars): "
                "provável absorção de outro item."
            )
        elif char_count > WARN_ALTERNATIVE_TEXT_CHARS:
            if TASK_VERB_IN_ALTERNATIVE_PATTERN.search(text):
                errors.append(
                    f"Alternativa {alt.letra} longa ({char_count} chars) com verbo de tarefa: "
                    "possível item absorvido."
                )
            else:
                warnings.append(f"Alternativa {alt.letra} longa ({char_count} chars).")
    return errors, warnings


def _validate_latex_leaks(question: Question) -> tuple[list[str], list[str]]:
    """Detecta LaTeX fora de ambiente matemático que não pôde ser auto-corrigido.

    A correção automática em _apply_deterministic_fixes trata o caso simples
    (texto todo sem $). Este validador captura o caso residual: texto misto onde
    parte já está em $...$ mas há LaTeX solto fora — difícil de corrigir sem IA.
    """
    errors: list[str] = []
    warnings: list[str] = []
    for alt in question.alternativas or []:
        text = alt.texto or ""
        outside = _text_outside_math(text)
        match = _LATEX_OUTSIDE_MATH_RE.search(outside)
        if match:
            warnings.append(
                f"Alternativa {alt.letra}: LaTeX fora de ambiente matemático "
                f"({match.group()!r} fora de $...$): provável artefacto OCR."
            )
    outside_enunciado = _text_outside_math(question.enunciado or "")
    match = _LATEX_OUTSIDE_MATH_RE.search(outside_enunciado)
    if match:
        warnings.append(
            f"Enunciado contém LaTeX fora de ambiente matemático "
            f"({match.group()!r} fora de $...$): provável artefacto OCR."
        )
    return errors, warnings


def _count_unescaped_dollars(text: str) -> int:
    return len(re.findall(r"(?<!\\)\$", text or ""))


def _has_latex_brace_mismatch(text: str) -> bool:
    if "\\" not in (text or "") and "$" not in (text or ""):
        return False
    return (text or "").count("{") != (text or "").count("}")


def _validate_math_syntax(question: Question) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    enunciado = question.enunciado or ""
    if _count_unescaped_dollars(enunciado) % 2 != 0:
        errors.append("Enunciado com delimitadores '$' desequilibrados: LaTeX provavelmente quebrado.")
    elif _has_latex_brace_mismatch(enunciado):
        warnings.append("Enunciado com chavetas desequilibradas em conteúdo LaTeX.")

    for alt in question.alternativas or []:
        text = alt.texto or ""
        if _count_unescaped_dollars(text) % 2 != 0:
            errors.append(
                f"Alternativa {alt.letra} com delimitadores '$' desequilibrados: LaTeX provavelmente quebrado."
            )
        elif _has_latex_brace_mismatch(text):
            warnings.append(f"Alternativa {alt.letra} com chavetas desequilibradas em conteúdo LaTeX.")

    return errors, warnings


def _validate_choice_precision(question: Question) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if question.tipo_item != "multiple_choice":
        return errors, warnings

    if question.alternativas and _ALTERNATIVES_IN_ENUNCIADO_PATTERN.search(question.enunciado or ""):
        errors.append("Enunciado ainda contém o bloco de alternativas: segmentação incorreta do item.")

    normalized_texts: list[str] = []
    for alt in question.alternativas or []:
        text = (alt.texto or "").strip()
        marker = _ALT_MARKER_PREFIX_RE.match(text)
        if marker:
            found = marker.group(1)
            if found != (alt.letra or "").strip().upper():
                errors.append(
                    f"Alternativa {alt.letra} começa com marcador '{found}': possível troca de letras."
                )
            else:
                warnings.append(
                    f"Alternativa {alt.letra} ainda contém marcador duplicado no texto."
                )
        normalized_texts.append(re.sub(r"\s+", " ", text).lower())

    non_empty = [text for text in normalized_texts if text]
    if len(non_empty) != len(set(non_empty)):
        errors.append("Existem alternativas com texto duplicado após normalização.")

    return errors, warnings


_LINE_MARKER_CANONICAL_RE = re.compile(r"(?m)^(\d{1,3}) \S")
_LINE_MARKER_RESIDUAL_RE = re.compile(
    r"[^\n](?:\s)(\d{1,3})(?:\s)[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ«]"
    r"|[A-Za-zÁ-ÿ](\d{1,3})[A-Za-zÁ-ÿ]"
)


def _validate_context_stem_line_numbers(question: Question) -> list[str]:
    """Gate obrigatório: todo context_stem tem de declarar se há numeração de linhas.

    - tem_numeracao_linhas=None → bloqueia (agente não verificou ainda).
    - linhas_verificadas=False → bloqueia (agente não conferiu o PDF).
    - tem_numeracao_linhas=True mas enunciado sem marcadores no formato canónico
      "\\n{N} …" → bloqueia.
    - tem_numeracao_linhas=False mas enunciado com resíduos que parecem marcadores
      fundidos (ex: "palavra5 outra", "texto. 10 Outra") → bloqueia.
    """
    errors: list[str] = []
    tem_num = question.tem_numeracao_linhas
    if tem_num is None:
        errors.append(
            "context_stem sem tem_numeracao_linhas definido: o agente deve conferir o PDF "
            "original e preencher true (texto tem marcadores de linha) ou false (não tem)."
        )
    if not question.linhas_verificadas:
        errors.append(
            "context_stem com linhas_verificadas=false: o agente deve conferir o PDF "
            "original, aplicar o formato canónico '\\n{N} …' a cada marcador presente, "
            "e só então marcar linhas_verificadas=true."
        )
    if tem_num is True:
        enunciado = question.enunciado or ""
        if not _LINE_MARKER_CANONICAL_RE.search(enunciado):
            errors.append(
                "context_stem declara tem_numeracao_linhas=true mas o enunciado não contém "
                "nenhum marcador no formato canónico '\\n{N} …' em início de linha."
            )
    if tem_num is False:
        enunciado = question.enunciado or ""
        if _LINE_MARKER_RESIDUAL_RE.search(enunciado):
            errors.append(
                "context_stem declara tem_numeracao_linhas=false mas o enunciado contém "
                "números que parecem resíduos de marcadores de linha fundidos ao texto."
            )
    return errors


def _validate_categorization_fields(question: Question) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not (question.tema or "").strip() or (question.tema or "").strip().lower() == "por categorizar":
        warnings.append("Tema ausente ou por categorizar.")
    if not (question.subtema or "").strip() or (question.subtema or "").strip().lower() == "por categorizar":
        warnings.append("Subtema ausente ou por categorizar.")
    if not (question.descricao_breve or "").strip():
        warnings.append("descricao_breve ausente.")
    if not question.tags:
        warnings.append("Tags ausentes.")
    if not question.reviewed:
        errors.append("Item ainda não foi revisto pelo agente (reviewed: false).")
    return errors, warnings


def _validate_enunciado_contamination(question: Question) -> list[str]:
    """Detecta metadados do exame infiltrados no enunciado (ex: '# COTAÇÕES', 'GRUPO I')."""
    errors: list[str] = []
    if METADATA_CONTAMINATION_PATTERN.search(question.enunciado or ""):
        errors.append(
            "Enunciado contém metadados do exame (ex: '# COTAÇÕES', 'GRUPO', 'Pág.'): "
            "provável contaminação da página de cotações ou cabeçalho."
        )
    return errors


def _validate_enunciado_fused_prefix(question: Question) -> list[str]:
    """Avisa quando o enunciado começa com o número do item fundido ao texto (artefacto OCR)."""
    warnings: list[str] = []
    enunciado = (question.enunciado or "").strip()
    if FUSED_NUMBER_PREFIX_PATTERN.match(enunciado):
        warnings.append(
            "Enunciado inicia com prefixo numérico fundido ao texto (artefacto OCR): "
            "o número do item não foi separado do enunciado."
        )
    return warnings


def _validate_stem_classification(question: Question, has_subitems: bool) -> list[str]:
    """Avisa quando um item de topo com subitens não contém verbo de tarefa.

    Itens assim são normalmente stems/contexto e podem estar classificados como
    'open_response' por engano. Não é erro porque o conteúdo pode ser válido;
    é um sinal para revisão manual.
    """
    warnings: list[str] = []
    if question.subitem is not None:
        return warnings
    if not has_subitems:
        return warnings
    if question.tipo_item == "multiple_choice":
        return warnings
    if not STEM_TASK_VERB_PATTERN.search(question.enunciado or ""):
        warnings.append(
            "Item de topo com subitens sem verbo de tarefa: pode ser stem/contexto "
            "classificado incorretamente como 'open_response'."
        )
    return warnings


def _validate_source_span_coverage(question: Question) -> list[str]:
    """Avisa quando o source_span cobre apenas 1 linha para um item com conteúdo não trivial."""
    warnings: list[str] = []
    if not question.source_span:
        return warnings
    line_start = question.source_span.get("line_start")
    line_end = question.source_span.get("line_end")
    if not isinstance(line_start, int) or not isinstance(line_end, int):
        return warnings
    if line_start == line_end:
        enunciado_chars = len(re.sub(r"\s+", "", question.enunciado or ""))
        if enunciado_chars > MIN_TEXT_LENGTH:
            warnings.append(
                f"source_span de 1 linha (linha {line_start}) para item com enunciado não trivial: "
                "possível sobreposição ou falha de segmentação."
            )
    return warnings


def _validate_missing_subitems(questions: list[Question]) -> dict[str, list[str]]:
    """Deteta quando um item referencia X.Y no seu texto mas esse subitem não existe na coleção.

    Exemplo: item 13 tem '13.1.' no enunciado mas não existe id_item '13.1' — sinal de que
    o Módulo 2 absorveu um grupo de subitens num único item.
    """
    errors_by_id: dict[str, list[str]] = {}
    existing_ids = {q.id_item for q in questions if q.id_item}
    for question in questions:
        if question.subitem is not None:
            continue  # subitens não precisam desta verificação
        main = question.numero_principal or question.numero_questao
        combined = (question.enunciado or "") + " " + (question.texto_original or "")
        refs_found: set[str] = set()
        for match in SUBITEM_REFERENCE_PATTERN.finditer(combined):
            ref_main = int(match.group(1))
            ref_sub = match.group(2)
            if ref_main == main:
                refs_found.add(f"{ref_main}.{ref_sub}")
        for expected_id in sorted(refs_found):
            if expected_id not in existing_ids:
                errors_by_id.setdefault(question.id_item, []).append(
                    f"Item referencia '{expected_id}' no texto mas esse subitem não existe na coleção: "
                    "provável fusão de subitens num único item."
                )
    return errors_by_id


def _format_estrutura(estrutura: dict[str, list[str]]) -> str:
    """Formata a estrutura de uma prova como string legível.
    Ex: '1, 2, 3[3.1,3.2], 4, 5[5.1,5.2,5.3]'
    """
    parts = []
    for main_str in sorted(estrutura, key=lambda x: int(x) if x.isdigit() else 0):
        subs = estrutura[main_str]
        if subs:
            parts.append(f"{main_str}[{','.join(sorted(subs))}]")
        else:
            parts.append(main_str)
    return ", ".join(parts)


def _build_json_estrutura(questions: list[Question]) -> dict[str, list[str]]:
    """Constrói o mapa estrutura equivalente ao das cotações a partir dos questions."""
    estrutura: dict[str, list[str]] = {}
    for q in questions:
        if q.tipo_item == "context_stem":
            continue  # context_stems não aparecem nas cotações
        main_str = q.id_item if q.subitem is None else str(q.numero_principal or q.numero_questao)
        if q.subitem is None:
            estrutura.setdefault(main_str, [])
        else:
            estrutura.setdefault(main_str, []).append(q.id_item)
    return estrutura


def _validate_against_cotacoes(
    questions: list[Question],
    cotacoes: EstruturaCotacoes,
) -> tuple[dict[str, list[str]], list[str], bool]:
    """Valida a estrutura do JSON estritamente contra a tabela de cotações.

    A tabela de cotações é a fonte de verdade: qualquer discrepância na numeração,
    subitens em falta, subitens extra, itens em falta ou itens extra deve ser
    sinalizada como erro obrigatório (não aviso) quando confiança não é 'baixa'.

    Retorna:
        errors_by_id:         erros atribuídos a questões específicas (por id_item)
        global_erros:         erros globais (itens em falta que não têm representante no JSON)
        estrutura_inconsistente: True se houver qualquer divergência estrutural
    """
    errors_by_id: dict[str, list[str]] = {}
    global_erros: list[str] = []
    estrutura_inconsistente = False

    # Quando a extracção teve baixa confiança, todas as violações são avisos (não bloqueiam)
    use_errors = cotacoes.confianca != "baixa"

    def _add(target_id: str | None, msg: str) -> None:
        nonlocal estrutura_inconsistente
        estrutura_inconsistente = True
        if target_id:
            errors_by_id.setdefault(target_id, []).append(msg)
        else:
            global_erros.append(msg)

    # Mapa: parent_id_item → lista de id_item de subitems presentes no JSON
    # "II-2.1" → parent "II-2"; "2.1" → parent "2"
    json_subs_by_main: dict[str, list[str]] = {}
    for q in questions:
        if q.subitem is not None:
            parent_id = re.sub(r"\.\d+$", "", q.id_item)
            json_subs_by_main.setdefault(parent_id, []).append(q.id_item)

    top_level_questions = [q for q in questions if q.subitem is None]
    # Indexar por id_item (suporta prefixo de grupo "I-1" e formato simples "1")
    top_level_by_num: dict[str, Question] = {}
    for q in top_level_questions:
        top_level_by_num[q.id_item] = q
        plain_key = str(q.numero_principal or q.numero_questao)
        if plain_key not in top_level_by_num:
            top_level_by_num[plain_key] = q

    def _cot_sort_key(k: str) -> tuple:
        """Ordena chaves de cotações: primeiro planas ("1","2"), depois por grupo ("I-1","II-2.1")."""
        m = re.match(r"^(?:([IVX]+)-)?(\d+)(?:\.(\d+))?$", k)
        if m:
            g = {"I": 0, "II": 1, "III": 2}.get(m.group(1) or "", -1)
            return (g, int(m.group(2)), int(m.group(3) or 0))
        return (-1, 0, 0)

    # 1. Itens principais nas cotações completamente ausentes do JSON
    for main_str in sorted(cotacoes.estrutura, key=_cot_sort_key):
        if main_str not in top_level_by_num:
            subs = cotacoes.estrutura[main_str]
            detail = f" (com subitens {sorted(subs)})" if subs else ""
            msg = (
                f"[ESTRUTURA] Item {main_str}{detail} consta das cotações mas está completamente "
                "ausente do JSON: item não foi extraído pelo Módulo 2."
            )
            if use_errors:
                _add(None, msg)
            else:
                global_erros.append(f"[baixa confiança] {msg}")

    # 2. Cross-reference de subitens por item principal
    for main_str, expected_subs in cotacoes.estrutura.items():
        cotacoes_subs_set = set(expected_subs)
        json_subs_set = set(json_subs_by_main.get(main_str, []))

        # 2a. Subitens nas cotações mas ausentes no JSON
        for sub_id in sorted(cotacoes_subs_set - json_subs_set):
            msg = (
                f"[ESTRUTURA] Subitem '{sub_id}' esperado pelas cotações não existe no JSON: "
                "fusão ou omissão no Módulo 2."
            )
            if use_errors:
                # Ao item pai (context_stem verificará antes de aprovar)
                _add(main_str, msg)
                # E a cada subitem existente do grupo (pelo menos um fica rejeitado)
                for existing_sub in sorted(json_subs_set):
                    _add(existing_sub, msg)
            else:
                global_erros.append(f"[baixa confiança] {msg}")

        # 2b. Subitens no JSON mas ausentes nas cotações
        for sub_id in sorted(json_subs_set - cotacoes_subs_set):
            msg = (
                f"[ESTRUTURA] Subitem '{sub_id}' existe no JSON mas não consta das cotações: "
                "numeração incorrecta ou subitem extra."
            )
            if use_errors:
                _add(sub_id, msg)
            else:
                global_erros.append(f"[baixa confiança] {msg}")

        # 2c. Cotações indica item simples, mas JSON tem subitems
        if not expected_subs and json_subs_set:
            sub_list = sorted(json_subs_set)
            msg = (
                f"[ESTRUTURA] Item {main_str} é simples nas cotações mas tem subitems {sub_list} "
                "no JSON: estrutura diverge."
            )
            if use_errors:
                _add(main_str, msg)
                for sub_id in sub_list:
                    _add(sub_id, msg)
            else:
                global_erros.append(f"[baixa confiança] {msg}")

        # 2d. Cotações indica item com subitens, mas JSON não tem nenhum
        if expected_subs and not json_subs_set:
            subs_esperados = sorted(expected_subs)
            # Só emitir se o item principal existir no JSON (caso contrário check 1 já cobriu)
            if main_str in top_level_by_num:
                msg = (
                    f"[ESTRUTURA] Item {main_str} deveria ter subitems {subs_esperados} "
                    "segundo as cotações, mas nenhum subitem existe no JSON."
                )
                if use_errors:
                    _add(main_str, msg)
                else:
                    global_erros.append(f"[baixa confiança] {msg}")

    # 3. Itens no JSON cujo id_item não está nas cotações (erro, não aviso)
    # Context_stems são excluídos: existem no JSON mas nunca nas cotações.
    if cotacoes.estrutura:
        cotacoes_item_ids = set(cotacoes.estrutura.keys())
        for q in top_level_questions:
            if q.tipo_item == "context_stem":
                continue
            plain_key = str(q.numero_principal or q.numero_questao)
            if q.id_item not in cotacoes_item_ids and plain_key not in cotacoes_item_ids:
                msg = (
                    f"[ESTRUTURA] Item {q.id_item} existe no JSON mas não consta das cotações: "
                    "item extra ou erro de numeração."
                )
                if use_errors:
                    _add(q.id_item, msg)
                else:
                    global_erros.append(f"[baixa confiança] {msg}")

    return errors_by_id, global_erros, estrutura_inconsistente


_MULTI_SELECT_AFFIRMATION_RE = re.compile(
    r"(?m)^\s*(?:[IVX]+\.|[IVX]+\s)\s+\S",  # "I. texto", "II. texto", "III. texto"
)
_TABLE_OR_IMAGE_RE = re.compile(r"!\[|^\|.+\|", re.MULTILINE)


def _validate_portugues_tipos(question: Question) -> tuple[list[str], list[str]]:
    """Validações específicas para tipos de questão de Português."""
    errors: list[str] = []
    warnings: list[str] = []

    if question.tipo_item == "essay":
        if not question.palavras_min and not question.palavras_max:
            warnings.append(
                "Tipo 'essay' sem palavras_min/palavras_max definidos: preencher manualmente."
            )

    if question.tipo_item == "multi_select":
        afirmacoes = _MULTI_SELECT_AFFIRMATION_RE.findall(question.enunciado or "")
        if len(afirmacoes) < 3:
            warnings.append(
                f"Tipo 'multi_select' com apenas {len(afirmacoes)} afirmações detectadas "
                "(esperado ≥ 3 afirmações I, II, III…): verificar enunciado."
            )

    if question.tipo_item == "complete_table":
        has_table = bool(_TABLE_OR_IMAGE_RE.search(question.enunciado or ""))
        has_image = bool(question.imagens)
        if not has_table and not has_image:
            warnings.append(
                "Tipo 'complete_table' sem imagem nem tabela no enunciado: "
                "quadro de opções provavelmente ausente."
            )

    return errors, warnings


def _validate_pt_stem_integrity(questions: list[Question]) -> tuple[dict[str, list[str]], list[str]]:
    """Verifica integridade da relação context_stem ↔ questões filhas.

    Erros:
    - id_contexto_pai não-vazio aponta para stem inexistente no mesmo grupo.
    Avisos:
    - context_stem sem nenhuma questão filha.
    """
    errors_by_id: dict[str, list[str]] = {}
    warnings: list[str] = []
    stem_ids = {q.id_item for q in questions if q.tipo_item == "context_stem" and q.id_item}
    stem_children: dict[str, int] = {sid: 0 for sid in stem_ids}
    for q in questions:
        if q.tipo_item == "context_stem":
            continue
        pais = q.ids_contexto_pai or ([q.id_contexto_pai] if q.id_contexto_pai else [])
        if not pais:
            continue
        for pai in pais:
            if pai not in stem_ids:
                errors_by_id.setdefault(q.id_item, []).append(
                    f"id_contexto_pai '{pai}' não corresponde a nenhum context_stem existente."
                )
            else:
                stem_children[pai] = stem_children.get(pai, 0) + 1
    for sid, count in stem_children.items():
        if count == 0:
            warnings.append(f"context_stem '{sid}' não tem nenhuma questão filha associada.")
    return errors_by_id, warnings


def _validate_pt_orphan_children(
    questions: list[Question],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Detecta questões órfãs (id_contexto_pai vazio) quando deveriam ter pai.

    Em provas PT, cada parte (A/B/C) ou grupo tem tipicamente um texto âncora
    (context_stem) que serve de pai para todas as questões daquela parte. Quando
    uma questão fica órfã mas existe um stem na mesma (grupo, parte), isto
    indica falha na atribuição automática — o agente deve ler o enunciado e
    preencher `id_contexto_pai` manualmente em questoes_review.json.

    Regras:
    - ERRO: existe context_stem na mesma (grupo, parte) → pai óbvio, deve ser preenchido.
    - AVISO: existem stems no mesmo grupo mas em partes diferentes → agente
      deve verificar se a questão refere o texto de alguma outra parte.
    - Silêncio: nenhum stem no grupo → órfã legítima.
    """
    errors_by_id: dict[str, list[str]] = {}
    warnings_by_id: dict[str, list[str]] = {}

    # Mapas: (grupo, parte) → id_item do stem; grupo → lista de (parte, id_item)
    stem_by_group_part: dict[tuple[str, str], str] = {}
    stems_by_group: dict[str, list[tuple[str, str]]] = {}
    for q in questions:
        if q.tipo_item != "context_stem" or not q.id_item:
            continue
        key = (q.grupo or "", q.parte or "")
        stem_by_group_part.setdefault(key, q.id_item)
        stems_by_group.setdefault(q.grupo or "", []).append((q.parte or "", q.id_item))

    for q in questions:
        if q.tipo_item == "context_stem":
            continue
        if q.ids_contexto_pai or q.id_contexto_pai:
            continue
        grupo = q.grupo or ""
        parte = q.parte or ""
        same_part_stem = stem_by_group_part.get((grupo, parte))
        same_group_stems = stems_by_group.get(grupo, [])
        if same_part_stem:
            errors_by_id.setdefault(q.id_item, []).append(
                f"Questão órfã: id_contexto_pai vazio mas existe context_stem "
                f"'{same_part_stem}' na mesma parte (grupo={grupo or '-'}, "
                f"parte={parte or '-'}). Ler o enunciado e preencher "
                f"id_contexto_pai='{same_part_stem}' em questoes_review.json."
            )
        elif same_group_stems:
            candidatos = ", ".join(
                f"'{sid}' (parte {p or '-'})" for p, sid in same_group_stems
            )
            warnings_by_id.setdefault(q.id_item, []).append(
                f"Questão órfã: id_contexto_pai vazio; não há stem na mesma parte "
                f"mas o grupo {grupo} tem outros textos ({candidatos}). Verificar "
                f"no enunciado se a questão refere algum desses textos e, se sim, "
                f"preencher id_contexto_pai em questoes_review.json."
            )
    return errors_by_id, warnings_by_id


def _validate_numbering_sequence(questions: list[Question]) -> dict[str, list[str]]:
    errors_by_id: dict[str, list[str]] = {}
    # Excluir context_stems: têm numero_principal=0 e não são questões numeradas
    top_level_ids = [
        question for question in questions
        if question.subitem is None and question.tipo_item != "context_stem"
    ]
    top_levels = [q.numero_principal or q.numero_questao for q in top_level_ids]
    if top_levels:
        expected = list(range(min(top_levels), max(top_levels) + 1))
        missing = [number for number in expected if number not in top_levels]
        if missing:
            message = f"Numeracao principal com lacunas: {missing}."
            for question in top_level_ids:
                errors_by_id.setdefault(question.id_item, []).append(message)

    grouped_subitems: dict[int, list[int]] = {}
    for question in questions:
        if question.subitem and question.subitem.isdigit():
            grouped_subitems.setdefault(question.numero_principal or question.numero_questao, []).append(int(question.subitem))
    for main_number, subitems in grouped_subitems.items():
        ordered = sorted(set(subitems))
        if not ordered:
            continue
        expected = list(range(1, ordered[-1] + 1))
        missing = [number for number in expected if number not in ordered]
        if missing:
            message = f"Subitens com lacunas no item {main_number}: {missing}."
            for question in questions:
                if (question.numero_principal or question.numero_questao) == main_number:
                    errors_by_id.setdefault(question.id_item, []).append(message)
    return errors_by_id


def validate_questions(raw_json_path: Path, materia: str = "") -> tuple[Path, Path]:
    raw_json_path = raw_json_path.resolve()
    output_dir = raw_json_path.parent
    images_root = output_dir
    is_pt = "portugu" in (materia or "").lower() or "portugu" in str(raw_json_path).lower()
    questions = load_questions(raw_json_path)
    questions = sorted(questions, key=_item_sort_key)

    # Limpar observações automáticas de runs anteriores antes de revalidar.
    # Caso contrário, erros já corrigidos continuariam a aparecer em q.observacoes
    # → vão para questoes_aprovadas.json → vão para o Supabase como observações
    # mentirosas. Apenas as notas geradas automaticamente pelos linters (com prefixo
    # conhecido) são removidas; observações humanas são preservadas.
    _AUTO_NOTE_PREFIXES = (
        "[validate][erro]",
        "[validate][aviso]",
        "[validate][corrigido]",
        "[micro-lint][erro]",
        "[micro-lint][aviso]",
        "[micro-lint][corrigido]",
    )
    for _q in questions:
        if _q.observacoes:
            _q.observacoes = [
                o for o in _q.observacoes
                if not any(o.startswith(pref) for pref in _AUTO_NOTE_PREFIXES)
            ]
    trace_map = _load_trace_map(raw_json_path)
    sequence_errors = _validate_numbering_sequence(questions)
    missing_subitem_errors = _validate_missing_subitems(questions)
    stem_integrity_errors, stem_integrity_warnings = (
        _validate_pt_stem_integrity(questions) if is_pt else ({}, [])
    )
    orphan_errors, orphan_warnings = (
        _validate_pt_orphan_children(questions) if is_pt else ({}, {})
    )

    # Carregar manifesto estrutural (gerado por module_cotacoes a partir da
    # secção COTAÇÕES do prova.md). É obrigatório: serve de fonte de verdade
    # para o conjunto canónico de IDs do exame.
    cotacoes_path = output_dir / "cotacoes_estrutura.json"
    cotacoes: EstruturaCotacoes | None = None
    cotacoes_global_erros: list[str] = []
    cotacoes_errors_by_id: dict[str, list[str]] = {}
    estrutura_inconsistente = False
    cotacoes_bypassed = False

    if not cotacoes_path.exists():
        raise FileNotFoundError(
            f"cotacoes_estrutura.json não encontrado em {output_dir}.\n"
            "  O manifesto estrutural é obrigatório — declara o conjunto canónico\n"
            "  de IDs do exame que será validado contra o JSON estruturado.\n"
            "  Acções:\n"
            "    1. Re-correr `run_stage(stage='extract')` se a secção COTAÇÕES\n"
            "       existe no prova.md mas o parser não foi executado.\n"
            "    2. Criar manualmente a partir do PDF se o parser falhou\n"
            "       (formato canónico: ver schemas.EstruturaCotacoes)."
        )

    try:
        cotacoes = load_cotacoes(cotacoes_path)
    except Exception as exc:
        # Erro de formato/schema: bloquear sempre — sem stub silencioso.
        raise ValueError(
            f"cotacoes_estrutura.json inválido: {exc}\n"
            f"  Caminho: {cotacoes_path}\n"
            "  Corrigir o ficheiro antes de re-correr o validate."
        ) from exc

    if cotacoes.confianca == "ausente" or not cotacoes.cotacoes:
        raise ValueError(
            f"cotacoes_estrutura.json é um stub (confianca='ausente' ou sem entradas).\n"
            f"  Caminho: {cotacoes_path}\n"
            "  Preencher manualmente a partir da tabela de cotações do PDF\n"
            "  antes de re-correr o validate."
        )

    if cotacoes.bypass_validation:
        # Escape hatch auditável: exige bypass_motivo (já validado em load_cotacoes).
        cotacoes_bypassed = True
        print(
            "[validate] ⚠️  cotacoes_estrutura.json com bypass_validation=true — "
            "cross-check estrutura IGNORADO."
        )
        print(f"[validate]    Motivo: {cotacoes.bypass_motivo}")
        print("[validate]    Outras validações por item continuam.")
        cotacoes = None
    else:
        cotacoes_errors_by_id, cotacoes_global_erros, estrutura_inconsistente = _validate_against_cotacoes(questions, cotacoes)
        # Validar pools opcionais: cada item declarado num pool deve existir no JSON.
        json_ids = {q.id_item for q in questions if q.tipo_item != "context_stem"}
        for pool in cotacoes.pool_opcional:
            for item_id in pool.get("itens", []):
                if item_id not in json_ids:
                    cotacoes_global_erros.append(
                        f"[POOL] Item '{item_id}' declarado em pool_opcional "
                        f"(escolher {pool.get('escolher')}) não existe no JSON."
                    )
                    estrutura_inconsistente = True
    # Conjunto de números principais que têm pelo menos um subitem
    main_numbers_with_subitems: set[int] = {
        q.numero_principal or q.numero_questao
        for q in questions
        if q.subitem is not None
    }
    duplicate_id_items = {
        item_id
        for item_id in {question.id_item for question in questions if question.id_item}
        if sum(1 for question in questions if question.id_item == item_id) > 1
    }
    duplicate_order_items = {
        order
        for order in {question.ordem_item or question.numero_questao for question in questions}
        if sum(1 for question in questions if (question.ordem_item or question.numero_questao) == order) > 1
    }

    approved: list[Question] = []
    rejected: list[Question] = []
    report_items: list[dict] = []
    previous_order: int | None = None
    previous_line_end: int | None = None

    for question in questions:
        current_order = question.ordem_item or question.numero_questao

        # Correcções determinísticas (sem IA): artefactos OCR simples resolvidos por regex
        det_fixes = _apply_deterministic_fixes(question)
        for fix in det_fixes:
            note = f"[validate][corrigido] {fix}"
            if note not in question.observacoes:
                question.observacoes.append(note)

        # context_stem items are structural containers, not answerable questions.
        # Skip all content validation, but DO check cotações structural errors
        # (e.g. a missing subitem is attached to the parent in errors_by_id).
        if question.tipo_item == "context_stem":
            ctx_errors = cotacoes_errors_by_id.get(question.id_item, [])
            ctx_errors = list(ctx_errors)
            ctx_errors.extend(_validate_figura_reference(question))
            ctx_warnings: list[str] = []
            cat_errors, cat_warnings = _validate_categorization_fields(question)
            ctx_errors.extend(cat_errors)
            ctx_warnings.extend(cat_warnings)
            if is_pt:
                ctx_errors.extend(_validate_context_stem_line_numbers(question))
            # Avisos de integridade stem↔filha (stem órfão)
            for warn in stem_integrity_warnings:
                if question.id_item in warn:
                    ctx_warnings.append(warn)
            _append_validation_notes(question, ctx_errors, ctx_warnings)
            if ctx_errors:
                question.status = "validation_error"
                rejected.append(question)
            else:
                question.status = "approved_with_warnings" if ctx_warnings else "approved"
                approved.append(question)
            report_items.append({
                "id_item": question.id_item,
                "ordem_item": question.ordem_item,
                "status": question.status,
                "errors": ctx_errors,
                "warnings": ctx_warnings,
            })
            previous_order = current_order
            if question.source_span and isinstance(question.source_span.get("line_end"), int):
                previous_line_end = question.source_span["line_end"]
            continue

        errors: list[str] = []
        warnings: list[str] = []

        errors.extend(_validate_item_identity(question))
        errors.extend(_validate_alternatives(question))
        errors.extend(_validate_source_span(question))
        text_errors, text_warnings = _validate_text_fields(question)
        errors.extend(text_errors)
        warnings.extend(text_warnings)
        errors.extend(_validate_images(question, images_root))
        errors.extend(_validate_figura_reference(question))

        # Módulo 3: novos checks heurísticos
        alt_errors, alt_warnings = _validate_alternative_content(question)
        errors.extend(alt_errors)
        warnings.extend(alt_warnings)
        errors.extend(_validate_enunciado_contamination(question))
        warnings.extend(_validate_enunciado_fused_prefix(question))
        # Validações LaTeX — apenas para Matemática
        if not is_pt:
            latex_errors, latex_warnings = _validate_latex_leaks(question)
            errors.extend(latex_errors)
            warnings.extend(latex_warnings)
            math_errors, math_warnings = _validate_math_syntax(question)
            errors.extend(math_errors)
            warnings.extend(math_warnings)
        else:
            # Validações específicas de Português
            pt_errors, pt_warnings = _validate_portugues_tipos(question)
            errors.extend(pt_errors)
            warnings.extend(pt_warnings)
        choice_errors, choice_warnings = _validate_choice_precision(question)
        errors.extend(choice_errors)
        warnings.extend(choice_warnings)
        categorization_errors, categorization_warnings = _validate_categorization_fields(question)
        errors.extend(categorization_errors)
        warnings.extend(categorization_warnings)
        has_subitems = (question.numero_principal or question.numero_questao) in main_numbers_with_subitems
        warnings.extend(_validate_stem_classification(question, has_subitems))
        warnings.extend(_validate_source_span_coverage(question))
        for missing_err in missing_subitem_errors.get(question.id_item, []):
            errors.append(missing_err)
        # Erros de integridade stem↔filha (id_contexto_pai inválido)
        for stem_err in stem_integrity_errors.get(question.id_item, []):
            if stem_err not in errors:
                errors.append(stem_err)
        # Erros/avisos de órfãs PT (id_contexto_pai vazio mas stem disponível)
        for orphan_err in orphan_errors.get(question.id_item, []):
            if orphan_err not in errors:
                errors.append(orphan_err)
        for orphan_warn in orphan_warnings.get(question.id_item, []):
            if orphan_warn not in warnings:
                warnings.append(orphan_warn)
        # Erros estruturais das cotações — sempre obrigatórios (não são avisos)
        for cotacoes_err in cotacoes_errors_by_id.get(question.id_item, []):
            if cotacoes_err not in errors:
                errors.append(cotacoes_err)

        trace_errors, trace_warnings = _validate_trace_signals(trace_map.get(_trace_key(question)))
        errors.extend(trace_errors)
        warnings.extend(trace_warnings)

        if previous_order is not None and current_order != previous_order + 1:
            errors.append(
                f"Ordem dos itens não sequencial: esperado {previous_order + 1}, encontrado {current_order}."
            )
        if question.id_item in duplicate_id_items:
            errors.append(f"Identificador de item duplicado: {question.id_item}.")
        if current_order in duplicate_order_items:
            errors.append(f"ordem_item duplicada: {current_order}.")
        for seq_error in sequence_errors.get(question.id_item, []):
            errors.append(seq_error)
        if previous_line_end is not None and question.source_span:
            current_line_start = question.source_span.get("line_start")
            if isinstance(current_line_start, int) and current_line_start < previous_line_end:
                warnings.append(
                    f"source_span sobreposto com item anterior (line_start={current_line_start}, anterior_end={previous_line_end})."
                )

        observation_signals = [note for note in question.observacoes if not _is_ignorable_observation(note)]
        if len(observation_signals) >= 4:
            warnings.append(f"Item com muitos sinais heurísticos prévios ({len(observation_signals)} observações).")

        _append_validation_notes(question, errors, warnings)
        if errors:
            question.status = "validation_error"
            rejected.append(question)
        else:
            question.status = "approved_with_warnings" if warnings else "approved"
            approved.append(question)
        report_items.append(
            {
                "id_item": question.id_item,
                "ordem_item": question.ordem_item,
                "status": question.status,
                "errors": errors,
                "warnings": warnings,
            }
        )
        previous_order = current_order
        if question.source_span and isinstance(question.source_span.get("line_end"), int):
            previous_line_end = question.source_span["line_end"]

    approved_path = output_dir / "questoes_aprovadas.json"
    rejected_path = output_dir / "questoes_com_erro.json"
    report_path = output_dir / "questoes_validacao_heuristica.json"
    dump_questions(approved_path, approved)
    dump_questions(rejected_path, rejected)

    cotacoes_summary: dict = {"cotacoes_encontradas": False}
    if cotacoes is not None:
        json_estrutura = _build_json_estrutura(questions)
        cotacoes_estrutura_fmt = _format_estrutura(cotacoes.estrutura)
        json_estrutura_fmt = _format_estrutura(json_estrutura)
        cotacoes_summary = {
            "cotacoes_encontradas": True,
            "confianca": cotacoes.confianca,
            "total_esperado": cotacoes.total_itens_principais,
            "total_encontrado": len({q.numero_principal or q.numero_questao for q in questions if q.subitem is None}),
            "estrutura_inconsistente": estrutura_inconsistente,
            "estrutura_cotacoes": cotacoes_estrutura_fmt,
            "estrutura_json": json_estrutura_fmt,
            "erros_globais_estrutura": cotacoes_global_erros,
        }
        # Aviso obrigatório no terminal se a estrutura não bater
        if estrutura_inconsistente:
            print("\n" + "=" * 70)
            print("  ESTRUTURA INCONSISTENTE — CORREÇÃO OBRIGATÓRIA")
            print("=" * 70)
            print(f"  Cotações: {cotacoes_estrutura_fmt}")
            print(f"  JSON:     {json_estrutura_fmt}")
            if cotacoes_global_erros:
                print("  Erros globais:")
                for err in cotacoes_global_erros:
                    print(f"    • {err}")
            print("=" * 70 + "\n")

    dump_json(
        report_path,
        {
            "source": str(raw_json_path),
            "total_itens": len(questions),
            "aprovadas": len(approved),
            "com_erro": len(rejected),
            "cotacoes_validacao": cotacoes_summary,
            "itens": report_items,
        },
    )
    return approved_path, rejected_path
