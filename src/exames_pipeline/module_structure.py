from __future__ import annotations

import re
import re as _re
import shutil
from pathlib import Path

from .config import Settings
from .schemas import Question, dump_json, dump_questions
from .utils import extract_inferred_alternatives, infer_fonte_from_path, split_markdown_question_blocks

_HEADING_PREFIX_RE = _re.compile(r"^\s*\d+(?:\.\d+)*\.?\s*")
_COTACOES_TRUNCATE_PATTERN = re.compile(
    r"(?m)^#{0,3}\s*COTA[ÇC][ÕO]ES\b",
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


def _build_draft_question(block, resolved_fonte: str, ctx: str) -> Question:
    alternatives = [
        {"letra": letter, "texto": text}
        for letter, text in extract_inferred_alternatives(block.raw_markdown)
    ]
    enunciado = _HEADING_PREFIX_RE.sub("", block.raw_markdown, count=1).strip()
    if alternatives:
        enunciado = _ALTERNATIVES_IN_ENUNCIADO_PATTERN.sub("", enunciado).strip()

    observacoes: list[str] = []
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
        materia="Matemática A",
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
    )


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
    markdown_text = markdown_path.read_text(encoding="utf-8")

    cotacoes_match = _COTACOES_TRUNCATE_PATTERN.search(markdown_text)
    if cotacoes_match:
        markdown_text = markdown_text[: cotacoes_match.start()]

    blocks = split_markdown_question_blocks(markdown_text)
    parent_context: dict[int, str] = {
        block.numero_principal: block.raw_markdown
        for block in blocks
        if block.is_context_stem
    }

    questions: list[Question] = []
    traces: list[dict] = []

    for block in blocks:
        if block.is_context_stem:
            q = Question(
                numero_questao=block.numero_principal,
                id_item=block.item_id,
                numero_principal=block.numero_principal,
                subitem=None,
                ordem_item=block.ordem_item,
                enunciado=_HEADING_PREFIX_RE.sub("", block.raw_markdown, count=1).strip(),
                tipo_item="context_stem",
                status="approved",
                fonte=resolved_fonte,
                imagens=block.imagens,
                imagens_contexto=block.imagens_contexto,
                source_span=block.source_span,
                texto_original=block.raw_markdown,
                grupo=block.grupo,
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

        ctx = parent_context.get(block.numero_principal, "") or block.section_context
        draft = _build_draft_question(block, resolved_fonte, ctx)
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
    _apply_group_ids(questions)

    raw_json_path = output_dir / "questoes_raw.json"
    traces_path = output_dir / "questoes_raw.traces.json"
    dump_questions(raw_json_path, questions)
    dump_json(traces_path, traces)
    return raw_json_path
