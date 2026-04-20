from __future__ import annotations

import re
import re as _re
import shutil
from pathlib import Path

from .config import Settings
from .schemas import Question, dump_json, dump_questions, split_question_for_review
from .utils import (
    _FONTE_PATTERN,
    _MATERIA_CODES,
    extract_inferred_alternatives,
    extract_notas_rodape,
    strip_notas_section,
    extract_pt_group_contexts,
    infer_fonte_from_path,
    is_optional_marker,
    normalize_pt_preamble_line_numbers,
    split_markdown_question_blocks,
)

_HEADING_PREFIX_RE = _re.compile(r"^\s*\d+(?:\.\d+)*\.?\s*")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Auto-correcções tipográficas PT (sem LaTeX)
_PT_AUTO_CORRECTIONS: list[tuple[re.Pattern[str], str]] = [
    # Aspas retas → aspas portuguesas (só fora de blocos de código/LaTeX)
    (re.compile(r'(?<![`$\\])"([^"]+)"'), r'«\1»'),
    # Reticências de três pontos → caractere único
    (re.compile(r'\.\.\.'), '…'),
]

# Mapeamento de artefactos OCR para dígitos sobrescritos. Aplicado só quando o
# número correspondente existe na secção NOTAS do mesmo excerto (gate anti-falso-
# positivo): confirma que há uma nota de rodapé com aquele número e que o caractere
# suspeito aparece imediatamente após uma letra minúscula (padrão «palavra²»).
_OCR_SUPERSCRIPT_CANDIDATES: dict[str, str] = {
    "®": "⁸",
    "©": "⁹",
    "°": "⁰",
}
_SUP_TO_DIGIT: dict[str, str] = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
}
_NOTAS_SECTION_RE = re.compile(
    r"(?mi)^#{0,3}\s*NOTAS\s*\n(?P<body>.+?)(?=\n#{1,3}\s|\Z)",
    re.DOTALL,
)
_NOTA_NUM_RE = re.compile(r"(?m)^(?P<num>\d+)\s+\S")


def _fix_ocr_superscripts(text: str) -> str:
    """Converte artefactos OCR (®©°) em dígitos sobrescritos, validando contra
    os números efectivamente listados em cada secção NOTAS do documento."""
    note_nums: set[str] = set()
    for m in _NOTAS_SECTION_RE.finditer(text):
        note_nums.update(_NOTA_NUM_RE.findall(m.group("body")))
    if not note_nums:
        return text
    result = text
    for ocr_char, sup in _OCR_SUPERSCRIPT_CANDIDATES.items():
        digit = _SUP_TO_DIGIT[sup]
        if digit not in note_nums:
            continue
        result = re.sub(
            rf"([a-záàâãéêíóôõúç])\{ocr_char}",
            rf"\1{sup}",
            result,
        )
    return result


def _pt_auto_correct(text: str) -> str:
    for pattern, replacement in _PT_AUTO_CORRECTIONS:
        text = pattern.sub(replacement, text)
    text = _fix_ocr_superscripts(text)
    return text


def _infer_materia_from_path(path: Path) -> str:
    """Infere a matéria a partir do padrão EX-<código> no caminho do ficheiro."""
    candidates = [path.stem] + [p.name for p in path.parents]
    for candidate in candidates:
        match = _FONTE_PATTERN.search(candidate)
        if match:
            return _MATERIA_CODES.get(match.group("materia"), match.group("materia"))
    return "Matemática A"


_COTACOES_TRUNCATE_PATTERN = re.compile(
    r"(?m)^#{0,3}\s*(?:COTA[ÇC][ÕO]ES|FIM)\b",
    re.IGNORECASE,
)
_ALTERNATIVES_IN_ENUNCIADO_PATTERN = re.compile(r"\s*\(A\)[\s\S]*$")

# Secções do prova.md que não contêm questões e devem ser ignoradas pelo agente.
# Tudo antes do primeiro "# GRUPO" ou do primeiro item numerado é capa/formulário.
_PRE_QUESTIONS_BOUNDARY_RE = re.compile(
    r"(?m)^#\s+GRUPO\s+[IVX\d]",
    re.IGNORECASE,
)


def _ensure_mineru_images_at_workspace_root(workspace_dir: Path) -> None:
    images_root = workspace_dir / "images"
    if images_root.exists():
        return
    for images_subdir in workspace_dir.rglob("images"):
        if images_subdir.is_dir() and images_subdir != images_root:
            try:
                first = next(images_subdir.iterdir(), None)
            except PermissionError:
                continue
            if first is not None:
                shutil.copytree(images_subdir, images_root, dirs_exist_ok=True)
                return


def _pre_questions_offset(markdown_text: str) -> int:
    """Retorna o índice de caractere onde as questões começam (após capa/formulário).

    Se não encontrar um cabeçalho GRUPO, devolve 0 (o documento começa directamente
    nas questões — provas mais antigas sem separação explícita de grupos).
    """
    m = _PRE_QUESTIONS_BOUNDARY_RE.search(markdown_text)
    return m.start() if m else 0


def _build_draft_question(block, resolved_fonte: str, resolved_materia: str, ctx: str) -> Question:
    alternatives = [
        {"letra": letter, "texto": text}
        for letter, text in extract_inferred_alternatives(block.raw_markdown)
    ]
    enunciado = _HEADING_PREFIX_RE.sub("", block.raw_markdown, count=1).strip()
    if alternatives:
        enunciado = _ALTERNATIVES_IN_ENUNCIADO_PATTERN.sub("", enunciado).strip()

    observacoes: list[str] = []
    for m in _CONTROL_CHAR_RE.finditer(block.raw_markdown):
        start = max(0, m.start() - 20)
        end = min(len(block.raw_markdown), m.end() + 20)
        snippet = block.raw_markdown[start:end].replace("\n", " ").strip()
        observacoes.append(
            f"OCR-SUSPECT: control_char U+{ord(m.group()):04X} '{snippet}'"
        )
    if block.suspected_numbering_reset:
        observacoes.append(
            f"Numeracao OCR suspeita: cabecalho original '{block.heading_label_raw}' normalizado para '{block.item_id}'."
        )
    if block.inferred_from_implicit_boundary:
        observacoes.append(
            f"Fronteira implicita inferida; bloco sem cabecalho numerado tratado como item '{block.item_id}'."
        )
        if block.implicit_boundary_reasons:
            observacoes.append("Razoes da fronteira implicita: " + "; ".join(block.implicit_boundary_reasons))

    return Question(
        numero_questao=block.numero_principal,
        enunciado=enunciado,
        alternativas=alternatives,
        id_item=block.item_id,
        ordem_item=block.ordem_item,
        numero_principal=block.numero_principal,
        subitem=block.subitem,
        tipo_item=block.inferred_type,
        materia=resolved_materia,
        tema="Por categorizar",
        subtema="Por categorizar",
        tags=[],
        imagens=block.imagens,
        imagens_contexto=block.imagens_contexto,
        pagina_origem=None,
        resposta_correta=None,
        fonte=resolved_fonte,
        status="draft",
        observacoes=observacoes,
        texto_original=block.raw_markdown,
        source_span=block.source_span,
        enunciado_contexto_pai=ctx,
        grupo=block.grupo,
        parte=getattr(block, "parte", "") or "",
        pool_opcional=block.pool_opcional,
    )


def _parte_from_id(id_item: str) -> str:
    """Extrai a letra de parte do id_item (ex: 'I-A-1' → 'A', 'I-1' → '')."""
    parts = id_item.split("-")
    return parts[1] if len(parts) >= 3 and parts[1] in ("A", "B", "C", "D") else ""


def _assign_id_contexto_pai(
    questions: list[Question],
    stem_id_map: dict[tuple[str, str], str] | None = None,
) -> None:
    """Atribui id_contexto_pai a cada questão não-stem.

    Se stem_id_map for fornecido (provas PT com pt_contexts), usa a parte extraída
    do id_item para fazer a correspondência exacta: 'I-A-1' → parte='A' →
    stem_id_map[('I','A')]. Fallback: stem do grupo raiz (parte='').

    Sem stem_id_map (provas antigas sem pt_contexts), usa o stem precedente mais
    próximo na ordem de documento — comportamento legado.
    """
    _GRUPO_ORDER = {"I": 0, "II": 1, "III": 2, "IV": 3, "V": 4}
    sorted_qs = sorted(
        questions,
        key=lambda q: (
            _GRUPO_ORDER.get(q.grupo, 9),
            q.ordem_item if q.ordem_item is not None else 99999,
        ),
    )
    active_stem: dict[str, str] = {}  # grupo → id_item do stem ativo (legado)
    for q in sorted_qs:
        if q.tipo_item == "context_stem":
            active_stem[q.grupo] = q.id_item
            continue
        if stem_id_map:
            parte = _parte_from_id(q.id_item or "")
            q.id_contexto_pai = (
                stem_id_map.get((q.grupo, parte), "")
                or stem_id_map.get((q.grupo, ""), "")
            )
        else:
            q.id_contexto_pai = active_stem.get(q.grupo, "")


def _apply_group_ids(questions: list[Question]) -> None:
    grupos: dict[int, list[str]] = {}
    for q in questions:
        key = q.numero_principal or q.numero_questao
        grupos.setdefault(key, []).append(q.id_item)

    def _id_sort_key(id_str: str) -> list[int]:
        try:
            return [int(p) for p in id_str.split(".")]
        except ValueError:
            return [0]

    for q in questions:
        key = q.numero_principal or q.numero_questao
        q.grupo_ids = sorted(grupos.get(key, [q.id_item]), key=_id_sort_key)



def structure_markdown(settings: Settings, markdown_path: Path, fonte: str = "") -> Path:
    markdown_path = markdown_path.resolve()
    output_dir = markdown_path.parent
    _ensure_mineru_images_at_workspace_root(output_dir)
    resolved_fonte = fonte or infer_fonte_from_path(markdown_path)
    resolved_materia = _infer_materia_from_path(markdown_path)
    raw_on_disk = markdown_path.read_text(encoding="utf-8")
    markdown_text = raw_on_disk

    cotacoes_match = _COTACOES_TRUNCATE_PATTERN.search(markdown_text)
    if cotacoes_match:
        cotacoes_tail = markdown_text[cotacoes_match.start():]
        markdown_text = markdown_text[: cotacoes_match.start()]
    else:
        cotacoes_tail = ""

    if resolved_materia == "Português":
        markdown_text = _pt_auto_correct(markdown_text)
        markdown_text = normalize_pt_preamble_line_numbers(markdown_text)
        # Persistir a normalização para que o agente reveja o mesmo texto que
        # o extractor usa. Guarda-se uma cópia bruta como prova_original.md só
        # na primeira vez; a secção COTAÇÕES é reanexada para preservar o
        # ficheiro completo.
        original_backup = markdown_path.with_name("prova_original.md")
        if not original_backup.exists():
            original_backup.write_text(raw_on_disk, encoding="utf-8")
        persisted = markdown_text + cotacoes_tail
        if persisted != raw_on_disk:
            markdown_path.write_text(persisted, encoding="utf-8")
    else:
        markdown_text = _latex_auto_correct(markdown_text)

    blocks = split_markdown_question_blocks(markdown_text)
    parent_context: dict[int, str] = {
        block.numero_principal: block.raw_markdown
        for block in blocks
        if block.is_context_stem
    }
    # Para provas de Português: preâmbulos de grupo/parte (excerto, texto expositivo, tema)
    pt_contexts: dict[tuple[str, str], str] = (
        extract_pt_group_contexts(markdown_text, blocks)
        if resolved_materia == "Português"
        else {}
    )

    questions: list[Question] = []
    traces: list[dict] = []

    for block in blocks:
        if block.is_context_stem:
            enunciado_ctx = _HEADING_PREFIX_RE.sub("", block.raw_markdown, count=1).strip()
            # Extrair notas de rodapé do excerto (Português) — ficam no campo observacoes
            # como JSON para serialização em contextos.notas_rodape no Supabase.
            notas = extract_notas_rodape(enunciado_ctx) if resolved_materia == "Português" else []
            enunciado_clean = strip_notas_section(enunciado_ctx) if notas else enunciado_ctx
            q = Question(
                numero_questao=block.numero_principal,
                id_item=block.item_id,
                numero_principal=block.numero_principal,
                subitem=None,
                ordem_item=block.ordem_item,
                enunciado=enunciado_clean,
                tipo_item="context_stem",
                status="approved",
                fonte=resolved_fonte,
                materia=resolved_materia,
                tema="Por categorizar",
                subtema="Por categorizar",
                tags=[],
                imagens=block.imagens,
                imagens_contexto=block.imagens_contexto,
                source_span=block.source_span,
                texto_original=block.raw_markdown,
                grupo=block.grupo,
                observacoes=(
                    [f"[notas_rodape] {__import__('json').dumps(notas, ensure_ascii=False)}"]
                    if notas else []
                ),
            )
            questions.append(q)
            traces.append(
                {
                    "numero_questao": block.numero_principal,
                    "id_item": block.item_id,
                    "ordem_item": block.ordem_item,
                    "source_span": block.source_span,
                    "suspected_numbering_reset": block.suspected_numbering_reset,
                    "inferred_from_implicit_boundary": block.inferred_from_implicit_boundary,
                    "implicit_boundary_score": block.implicit_boundary_score,
                    "implicit_boundary_reasons": block.implicit_boundary_reasons,
                    "provider": "none",
                    "model": "none",
                    "error": None,
                    "question": q.to_dict(),
                }
            )
            continue

        ctx = (
            parent_context.get(block.numero_principal, "")
            or pt_contexts.get((block.grupo, block.parte), "")
            or pt_contexts.get((block.grupo, ""), "")
        )
        draft = _build_draft_question(block, resolved_fonte, resolved_materia, ctx)
        questions.append(draft)
        traces.append(
            {
                "numero_questao": block.numero_principal,
                "id_item": block.item_id,
                "ordem_item": block.ordem_item,
                "source_span": block.source_span,
                "suspected_numbering_reset": block.suspected_numbering_reset,
                "inferred_from_implicit_boundary": block.inferred_from_implicit_boundary,
                "implicit_boundary_score": block.implicit_boundary_score,
                "implicit_boundary_reasons": block.implicit_boundary_reasons,
                "provider": "draft",
                "model": "none",
                "error": None,
                "question": draft.to_dict(),
            }
        )

    questions = sorted(
        questions,
        key=lambda q: (
            q.ordem_item or q.numero_questao,
            q.numero_principal or q.numero_questao,
            int(q.subitem) if q.subitem and q.subitem.isdigit() else 0,
        ),
    )

    # Criar context_stem sintéticos para preâmbulos de grupo/parte PT
    # (excerto literário, texto expositivo, tema de dissertação)
    # IDs: I-ctx1, I-ctx2, II-ctx1, III-ctx1  (sequencial por grupo, por ordem de documento)
    stem_id_map: dict[tuple[str, str], str] = {}
    if pt_contexts:
        import json as _json
        _GRUPO_ORDER = {"I": 0, "II": 1, "III": 2, "IV": 3, "V": 4}
        pt_stems: list[Question] = []
        grupo_ctx_counter: dict[str, int] = {}
        ordered_contexts = sorted(
            pt_contexts.items(), key=lambda kv: (_GRUPO_ORDER.get(kv[0][0], 9), kv[0][1])
        )

        # Passo 1: construir stem_id_map antes de criar os stems
        for (grupo, parte), _ in ordered_contexts:
            grupo_ctx_counter[grupo] = grupo_ctx_counter.get(grupo, 0) + 1
            stem_id_map[(grupo, parte)] = f"{grupo}-ctx{grupo_ctx_counter[grupo]}"

        # Passo 2: criar stems com ordem_item baseada na primeira questão filha da parte
        # Stems da mesma parte (ex: PARTE A) são colocados antes das suas questões.
        # Stems sem questões próprias (ex: preâmbulo geral do grupo) ficam antes de tudo no grupo.
        import math as _math
        for (grupo, parte), preamble in ordered_contexts:
            stem_id = stem_id_map[(grupo, parte)]
            notas = extract_notas_rodape(preamble)
            preamble_clean = strip_notas_section(preamble) if notas else preamble
            obs: list[str] = (
                [f"[notas_rodape] {_json.dumps(notas, ensure_ascii=False)}"]
                if notas else []
            )
            # Encontrar a primeira questão desta parte para calcular a posição do stem
            parte_qs = [
                q for q in questions
                if q.grupo == grupo
                and q.tipo_item != "context_stem"
                and _parte_from_id(q.id_item or "") == parte
            ]
            if not parte_qs and parte == "":
                # Preâmbulo do grupo: vai antes de qualquer questão do grupo
                parte_qs = [
                    q for q in questions
                    if q.grupo == grupo and q.tipo_item != "context_stem"
                ]
            parte_qs.sort(key=lambda q: q.ordem_item or 99999)
            if parte_qs:
                # Stem fica no float order (first_order - 0.5) — depois de quantizado
                # e reordenado, aparece imediatamente antes da primeira questão filha
                stem_float = (parte_qs[0].ordem_item or 1) - 0.5
            elif parte != "":
                # Parte com texto mas sem questões (ex: enunciado de dissertação sem número)
                # → colocar após todas as questões do grupo (não no início)
                grupo_qs = [q for q in questions if q.grupo == grupo and q.tipo_item != "context_stem"]
                last_order = max((q.ordem_item or 0) for q in grupo_qs) if grupo_qs else 0
                stem_float = last_order + 0.5
            else:
                # Preâmbulo geral do grupo (parte='') sem nenhuma questão no grupo →
                # posicionar após as questões dos grupos anteriores, para respeitar
                # a ordem do grupo (ex.: III-ctx1 deve aparecer depois de todo o Grupo II)
                prev_grupos = {
                    g for g, order in _GRUPO_ORDER.items()
                    if order < _GRUPO_ORDER.get(grupo, 9)
                }
                prev_qs = [
                    q for q in questions
                    if q.grupo in prev_grupos and q.tipo_item != "context_stem"
                ]
                stem_float = (
                    max((q.ordem_item or 0) for q in prev_qs) + 0.5
                    if prev_qs else 0.0
                )
            pt_stems.append(Question(
                numero_questao=0,
                enunciado=preamble_clean,
                id_item=stem_id,
                ordem_item=_math.ceil(stem_float),  # temporário; resequenciado abaixo
                numero_principal=0,
                tipo_item="context_stem",
                status="approved",
                fonte=resolved_fonte,
                materia=resolved_materia,
                tema="Por categorizar",
                subtema="Por categorizar",
                tags=[],
                grupo=grupo,
                parte=parte,
                reviewed=False,
                texto_original=preamble,
                observacoes=obs,
            ))

        # Passo 3: fundir + ordenar por (float_order, tipo) + reatribuir ordem sequencial
        # Usamos o stem_id para desempate: I-ctx1 < I-ctx2 < I-ctx3 (ordem de documento)
        all_items = questions + pt_stems
        all_items.sort(key=lambda q: (
            (q.ordem_item if q.ordem_item is not None else 99999)
            + (0 if q.tipo_item == "context_stem" else 0.5),
            q.id_item or "",
        ))
        for seq, q in enumerate(all_items, start=1):
            q.ordem_item = seq
        questions = all_items

    _apply_group_ids(questions)
    _assign_id_contexto_pai(questions, stem_id_map if stem_id_map else None)

    raw_json_path = output_dir / "questoes_raw.json"
    traces_path = output_dir / "questoes_raw.traces.json"
    dump_questions(raw_json_path, questions)
    dump_json(traces_path, traces)

    # Gerar ficheiros de review compactos para o agente:
    # questoes_review.json — apenas campos que o agente lê/edita
    # questoes_meta.json   — campos estruturais usados pelo validador internamente
    review_items: list[dict] = []
    meta_items: list[dict] = []
    for q in questions:
        review, meta = split_question_for_review(q.to_dict())
        review_items.append(review)
        meta_items.append(meta)
    dump_json(output_dir / "questoes_review.json", review_items)
    dump_json(output_dir / "questoes_meta.json", meta_items)

    return raw_json_path
