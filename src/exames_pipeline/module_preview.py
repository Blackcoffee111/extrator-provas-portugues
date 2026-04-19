"""
Módulo Preview — Preview interativo das questões aprovadas.

Abre um servidor HTTP local e exibe um HTML com todas as questões.
O utilizador pode:
  - Aprovar questões com erro (✅ move de questoes_com_erro.json para questoes_aprovadas.json)
  - Editar enunciado ou alternativas de qualquer questão
  - Editar cabeçalho (id_item, tipo_item, resposta_correta)
  - Rever e corrigir manualmente antes da aprovação final para upload
"""
from __future__ import annotations

import copy
import html
import http.server
import json
import re
import socketserver
import threading
import webbrowser
from pathlib import Path

from . import overlay as overlay_mod
from .schemas import Question, dump_questions, load_questions

_DEFAULT_PORT = 8798

# ── Conversão Markdown/LaTeX → HTML ──────────────────────────────────────────

_BLOCK_MATH_RE  = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\$(?!\$)(.+?)\$", re.DOTALL)
_BOLD_RE        = re.compile(r"\*\*(.+?)\*\*")
_BULLET_RE      = re.compile(r"(?m)^[•\-]\s+(.+)$")
_IMAGE_MD_RE    = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_TABLE_RE       = re.compile(r"<table[\s\S]*?</table>", re.IGNORECASE)


def _md_to_html(text: str) -> str:
    """Converte Markdown/LaTeX para HTML com URLs de imagem relativas ao servidor."""
    block_math: list[str] = []
    inline_math: list[str] = []
    tables: list[str] = []

    def save_block(m: re.Match) -> str:
        block_math.append(m.group(0))
        return f"\x00BM{len(block_math)-1}\x00"

    def save_inline(m: re.Match) -> str:
        inline_math.append(m.group(0))
        return f"\x00IM{len(inline_math)-1}\x00"

    def save_table(m: re.Match) -> str:
        tables.append(m.group(0))
        return f"\x00TB{len(tables)-1}\x00"

    # Guardar tabelas antes do escape (são HTML literal do OCR)
    text = _TABLE_RE.sub(save_table, text)
    text = _BLOCK_MATH_RE.sub(save_block, text)
    text = _INLINE_MATH_RE.sub(save_inline, text)
    text = html.escape(text)

    def replace_image(m: re.Match) -> str:
        src = html.unescape(m.group(1))
        # URLs completas (Supabase Storage) são usadas diretamente;
        # caminhos locais são servidos via endpoint do servidor local.
        if src.startswith("http://") or src.startswith("https://"):
            url = src
        else:
            url = src.lstrip("/")
        return f'<img class="q-img" src="{html.escape(url)}" alt="">'

    text = _IMAGE_MD_RE.sub(replace_image, text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _BULLET_RE.sub(r"<li>\1</li>", text)
    text = re.sub(r"(<li>.*?</li>)+", lambda m: f"<ul>{m.group(0)}</ul>", text, flags=re.DOTALL)

    paragraphs = re.split(r"\n{2,}", text.strip())
    parts: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith(("<ul>", "\x00BM", "\x00TB")):
            parts.append(p)
        elif "<ul>" in p:
            # Parágrafo misto: texto + lista — separar para evitar <p><ul></p>
            segments = re.split(r"(<ul>.*?</ul>)", p, flags=re.DOTALL)
            for seg in segments:
                seg = seg.strip()
                if not seg:
                    continue
                if seg.startswith("<ul>"):
                    parts.append(seg)
                else:
                    parts.append(f"<p>{seg.replace(chr(10), '<br>')}</p>")
        else:
            parts.append(f"<p>{p.replace(chr(10), '<br>')}</p>")
    text = "\n".join(parts)

    for i, m in enumerate(block_math):
        text = text.replace(f"\x00BM{i}\x00",
                            f'<span class="math-block">\\[{m[2:-2]}\\]</span>')
    for i, m in enumerate(inline_math):
        text = text.replace(f"\x00IM{i}\x00", f'\\({m[1:-1]}\\)')
    for i, t in enumerate(tables):
        text = text.replace(f"\x00TB{i}\x00",
                            f'<div class="ocr-table-wrap">{t}</div>')
    return text


# ── Badges ────────────────────────────────────────────────────────────────────

def _override_badge(field: str, overrides: dict[str, str]) -> str:
    """Badge colorido se o campo tiver um override activo."""
    source = overrides.get(field)
    if source == "human":
        return (
            '<span class="override-badge override-human" '
            'title="Editado manualmente pelo utilizador">✏️ manual</span>'
        )
    if source == "agent":
        return (
            '<span class="override-badge override-agent" '
            'title="Editado pelo agente">🤖 agente</span>'
        )
    return ""


def _status_badge(status: str) -> str:
    colours = {
        "approved":               ("✅", "#22c55e"),
        "approved_with_warnings": ("⚠️",  "#f59e0b"),
        "error":                  ("❌", "#ef4444"),
        "manual_review_required": ("🔧", "#ef4444"),
        "pending_review":         ("⏳", "#94a3b8"),
    }
    emoji, colour = colours.get(status, ("?", "#94a3b8"))
    label = status.replace("_", " ")
    return (f'<span class="badge" style="background:{colour}20;color:{colour};'
            f'border:1px solid {colour}60">{emoji} {label}</span>')


# ── Renderização de questão ───────────────────────────────────────────────────

def _render_question(q: Question, index: int, show_context: bool = True, overrides: dict[str, str] | None = None) -> str:
    """Renderiza uma questão em HTML.

    overrides: {field: source} onde source é "human" ou "agent".
    """
    overrides = overrides or {}
    item_id  = html.escape(q.id_item or str(q.numero_questao))
    tipo     = q.tipo_item or "unknown"
    status   = q.status or "pending_review"
    fonte    = html.escape(q.fonte or "")
    resposta = html.escape(q.resposta_correta or "")

    # ── Cabeçalho com edição inline ──────────────────────────────────────────
    mc_answer_field = ""
    if tipo == "multiple_choice":
        mc_answer_field = (
            f' <span class="header-label">Opção</span>'
            f'<input class="header-input mc-resp-input" size="2" maxlength="1"'
            f' value="{resposta}" data-field="resposta_correta"'
            f' placeholder="A-D" title="Resposta correcta (A/B/C/D)">'
        )

    approve_btn = ""
    if status == "error":
        approve_btn = (
            f'<button class="approve-btn" title="Aprovar esta questão"'
            f' onclick="approveQuestion(this,\'{item_id}\')">✅ Aprovar</button>'
        )

    header = f"""
  <header class="q-header">
    <span class="header-label">#</span>
    <input class="header-input id-input" size="5" value="{item_id}"
      data-field="id_item" title="Editar id do item" data-orig="{item_id}">
    <select class="header-select tipo-select" data-field="tipo_item" title="Tipo">
      <option value="multiple_choice"{'selected' if tipo=='multiple_choice' else ''}>EM</option>
      <option value="open_response"{'selected' if tipo=='open_response' else ''}>RD</option>
      <option value="context_stem"{'selected' if tipo=='context_stem' else ''}>CTX</option>
      <option value="composite"{'selected' if tipo=='composite' else ''}>CP</option>
    </select>
    {_status_badge(status)}
    {mc_answer_field}
    <button class="header-save-btn" onclick="saveHeader(this)"
      data-orig-id="{item_id}" style="display:none">💾</button>
    {approve_btn}
    <span class="q-fonte">{fonte}</span>
  </header>"""

    # ── Contexto pai (enunciado partilhado) ──────────────────────────────────
    contexto_block = ""
    if show_context and q.enunciado_contexto_pai:
        ctx_raw  = q.enunciado_contexto_pai
        ctx_html = _md_to_html(ctx_raw)
        ctx_esc  = html.escape(ctx_raw)
        contexto_block = f"""
  <div class="field-block context-block">
    <div class="field-label" style="color:#6b7280">Contexto
      {_override_badge("enunciado_contexto_pai", overrides)}
      <button class="edit-btn" onclick="toggleEdit(this)" title="Editar"
        data-item="{item_id}" data-field="enunciado_contexto_pai">✏️</button>
    </div>
    <div class="field-text enunciado-text" style="background:#f0f9ff;border-left:3px solid #3b82f6;padding-left:10px">{ctx_html}</div>
    <div class="edit-area" style="display:none">
      <textarea class="edit-ta" rows="10">{ctx_esc}</textarea>
      <div class="edit-actions">
        <button class="save-btn" onclick="saveEdit(this)"
          data-item="{item_id}" data-field="enunciado_contexto_pai">Guardar</button>
        <button class="cancel-btn" onclick="cancelEdit(this)">Cancelar</button>
      </div>
    </div>
  </div>"""

    # ── Enunciado ────────────────────────────────────────────────────────────
    enunciado_raw = q.enunciado or ""
    enunciado_html = _md_to_html(enunciado_raw)
    enunciado_esc  = html.escape(enunciado_raw)

    enunciado_block = f"""
  <div class="field-block">
    <div class="field-label">Enunciado
      {_override_badge("enunciado", overrides)}
      <button class="edit-btn" onclick="toggleEdit(this)" title="Editar"
        data-item="{item_id}" data-field="enunciado">✏️</button>
    </div>
    <div class="field-text enunciado-text">{enunciado_html}</div>
    <div class="edit-area" style="display:none">
      <textarea class="edit-ta" rows="5">{enunciado_esc}</textarea>
      <div class="edit-actions">
        <button class="save-btn" onclick="saveEdit(this)"
          data-item="{item_id}" data-field="enunciado">Guardar</button>
        <button class="cancel-btn" onclick="cancelEdit(this)">Cancelar</button>
      </div>
    </div>
  </div>"""

    # ── Alternativas (MC) ────────────────────────────────────────────────────
    alts_badge = _override_badge("alternativas", overrides)
    alts_block = ""
    if q.alternativas:
        items_html = ""
        for alt in q.alternativas:
            letra = getattr(alt, "letra", alt.get("letra", "?") if isinstance(alt, dict) else "?")
            texto = getattr(alt, "texto", alt.get("texto", "") if isinstance(alt, dict) else "")
            texto_html = _md_to_html(texto)
            texto_esc  = html.escape(texto)
            letra_esc  = html.escape(str(letra))
            items_html += f"""
    <li data-letra="{letra_esc}">
      <span class="alt-letter">{letra_esc}</span>
      <span class="alt-text field-text">{texto_html}</span>
      <button class="edit-btn" onclick="toggleAltEdit(this)" title="Editar alternativa"
        data-item="{item_id}" data-letra="{letra_esc}">✏️</button>
      <div class="edit-area" style="display:none">
        <textarea class="edit-ta" rows="3">{texto_esc}</textarea>
        <div class="edit-actions">
          <button class="save-btn" onclick="saveAltEdit(this)"
            data-item="{item_id}" data-letra="{letra_esc}">Guardar</button>
          <button class="cancel-btn" onclick="cancelEdit(this)">Cancelar</button>
        </div>
      </div>
    </li>"""
        alts_block = f'<div class="alts-label">{alts_badge}</div><ol class="alternatives">{items_html}</ol>'

    # ── Critérios de Classificação (CC) ──────────────────────────────────────
    cc_block = ""
    has_cc = q.solucao or q.criterios_parciais or q.resolucoes_alternativas
    if has_cc:
        cc_parts = ""
        cc_badge     = _override_badge("criterios_parciais", overrides)
        solucao_badge = _override_badge("solucao", overrides)

        # Critérios parciais — cada linha editável
        if q.criterios_parciais:
            rows_html = ""
            for ci, cp in enumerate(q.criterios_parciais):
                pts      = html.escape(str(cp.get("pontos", "?")))
                desc_raw = str(cp.get("descricao", ""))
                desc_html = _md_to_html(desc_raw)
                desc_esc  = html.escape(desc_raw)
                rows_html += f"""<tr class="cc-row" data-cc-idx="{ci}">
  <td class="pts-cell">
    <div class="cc-row-content"><span class="pts-display">{pts} pts</span></div>
    <div class="cc-edit-area" style="display:none">
      <input class="cc-pts-input" type="number" min="0" max="20" value="{pts}" size="3">
      <span class="pts-label">pts</span>
    </div>
  </td>
  <td>
    <div class="cc-row-content">
      <span class="cc-desc-text">{desc_html}</span>
      <button class="cc-edit-btn" onclick="toggleCcEdit(this)" title="Editar critério">✏️</button>
      <button class="delete-btn" onclick="deleteCcRow(this)"
        data-item="{item_id}" data-cc-idx="{ci}" title="Remover critério">🗑️</button>
    </div>
    <div class="cc-edit-area" style="display:none">
      <textarea class="cc-desc-ta" rows="2">{desc_esc}</textarea>
      <div class="edit-actions">
        <button class="save-btn" onclick="saveCcEdit(this)"
          data-item="{item_id}" data-cc-idx="{ci}">Guardar</button>
        <button class="cancel-btn" onclick="cancelCcEdit(this)">Cancelar</button>
      </div>
    </div>
  </td>
</tr>"""
            add_row_btn = (f'<button class="cc-add-btn" onclick="addCcRow(this)"'
                           f' data-item="{item_id}">+ Adicionar critério</button>')
            cc_parts += (f'<details class="cc-det" open>'
                         f'<summary>Critérios parciais ({len(q.criterios_parciais)}) {cc_badge}</summary>'
                         f'<table class="cc-table"><thead><tr><th>Pts</th><th>Descrição</th></tr></thead>'
                         f'<tbody class="cc-tbody">{rows_html}</tbody></table>'
                         f'{add_row_btn}</details>')
            # Solução completa colapsada
            if q.solucao:
                solucao_esc = html.escape(q.solucao)
                cc_parts += (f'<details class="cc-det">'
                             f'<summary>Ver resolução completa</summary>'
                             f'<div class="field-block cc-solucao-block">'
                             f'<div class="field-label">Resolução {solucao_badge}'
                             f' <button class="edit-btn" onclick="toggleEdit(this)" title="Editar"'
                             f' data-item="{item_id}" data-field="solucao">✏️</button></div>'
                             f'<div class="field-text cc-solucao">{_md_to_html(q.solucao)}</div>'
                             f'<div class="edit-area" style="display:none">'
                             f'<textarea class="edit-ta" rows="8">{solucao_esc}</textarea>'
                             f'<div class="edit-actions">'
                             f'<button class="save-btn" onclick="saveEdit(this)"'
                             f' data-item="{item_id}" data-field="solucao">Guardar</button>'
                             f'<button class="cancel-btn" onclick="cancelEdit(this)">Cancelar</button>'
                             f'</div></div></div></details>')
        elif q.solucao:
            solucao_esc = html.escape(q.solucao)
            cc_parts += (f'<div class="field-block cc-solucao-block">'
                         f'<div class="field-label">Resolução'
                         f' <button class="edit-btn" onclick="toggleEdit(this)" title="Editar"'
                         f' data-item="{item_id}" data-field="solucao">✏️</button></div>'
                         f'<div class="field-text cc-solucao">{_md_to_html(q.solucao)}</div>'
                         f'<div class="edit-area" style="display:none">'
                         f'<textarea class="edit-ta" rows="8">{solucao_esc}</textarea>'
                         f'<div class="edit-actions">'
                         f'<button class="save-btn" onclick="saveEdit(this)"'
                         f' data-item="{item_id}" data-field="solucao">Guardar</button>'
                         f'<button class="cancel-btn" onclick="cancelEdit(this)">Cancelar</button>'
                         f'</div></div></div>')

        # Resoluções alternativas — cada item editável
        if q.resolucoes_alternativas:
            alts = ""
            for ai, alt in enumerate(q.resolucoes_alternativas, 0):
                alt_esc = html.escape(alt)
                alts += f"""<li class="cc-alt-item" data-alt-idx="{ai}">
  <div class="cc-row-content">
    <strong>{ai + 2}.º Processo</strong><br>{_md_to_html(alt)}
    <button class="cc-edit-btn" onclick="toggleAltResEdit(this)" title="Editar">✏️</button>
  </div>
  <div class="cc-edit-area" style="display:none">
    <textarea class="cc-altres-ta" rows="5">{alt_esc}</textarea>
    <div class="edit-actions">
      <button class="save-btn" onclick="saveAltResEdit(this)"
        data-item="{item_id}" data-alt-idx="{ai}">Guardar</button>
      <button class="cancel-btn" onclick="cancelAltResEdit(this)">Cancelar</button>
    </div>
  </div>
</li>"""
            cc_parts += (f'<details class="cc-det">'
                         f'<summary>Processos alternativos ({len(q.resolucoes_alternativas)})</summary>'
                         f'<ol class="cc-alt-list">{alts}</ol></details>')

        # Resposta correta (MC)
        resp_badge = ""
        if q.resposta_correta and q.tipo_item == "multiple_choice":
            resp_badge = (f'<div class="cc-resposta">Resposta correta: '
                          f'<strong class="cc-letra">{html.escape(q.resposta_correta)}</strong></div>')

        cc_block = f"""
  <div class="cc-section">
    <div class="cc-section-label">Critérios de Classificação</div>
    {resp_badge}
    {cc_parts}
  </div>"""

    # ── Imagens extras ────────────────────────────────────────────────────────
    inline_imgs = set(_IMAGE_MD_RE.findall(enunciado_raw))
    extra_imgs  = [img for img in (q.imagens or []) if img not in inline_imgs]
    imgs_html   = ""
    if extra_imgs:
        def _img_src(p: str) -> str:
            return p if (p.startswith("http://") or p.startswith("https://")) else "/" + p.lstrip("/")
        imgs_html = '<div class="q-images">' + "".join(
            f'<img class="q-img" src="{html.escape(_img_src(p))}" alt="{html.escape(p.split("/")[-1])}">'
            for p in extra_imgs
        ) + "</div>"

    # ── Footer ────────────────────────────────────────────────────────────────
    obs_filtered = [o for o in (q.observacoes or []) if not o.startswith("Fornecedor")]
    obs_html = ""
    if obs_filtered:
        lis = "".join(f"<li>{html.escape(o)}</li>" for o in obs_filtered)
        obs_html = (f'<details class="obs-det"><summary>Observações ({len(obs_filtered)})</summary>'
                    f'<ul>{lis}</ul></details>')

    descricao_html = (f'<p class="descricao-breve">{html.escape(q.descricao_breve)}</p>'
                      if q.descricao_breve else "")
    meta = ""
    if q.materia:
        meta = (f'<span class="meta-item">📚 {html.escape(q.materia)}</span>'
                f'<span class="meta-item">📂 {html.escape(q.tema or "")}</span>'
                f'<span class="meta-item">🔖 {html.escape(q.subtema or "")}</span>')
    tags = " ".join(f'<span class="tag">#{t.lstrip("#")}</span>' for t in (q.tags or []))

    is_subitem   = q.subitem is not None
    extra_class  = " is-subitem" if is_subitem else ""
    error_class  = " error-item" if status == "error" else ""

    return f"""
<article class="question{extra_class}{error_class}" id="q{index}" data-id="{item_id}">
  {header}
  <div class="q-body">
    {contexto_block}
    {enunciado_block}
    {alts_block}
    {imgs_html}
  </div>
  {cc_block}
  <footer class="q-footer">
    {descricao_html}
    {meta}
    <div class="tags">{tags}</div>
    {obs_html}
  </footer>
</article>"""


# ── Template HTML ──────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Preview Questões</title>
<script>
MathJax = {{
  tex: {{ inlineMath: [['\\\\(','\\\\)'],['$','$']], displayMath: [['\\\\[','\\\\]'],['$$','$$']] }},
  options: {{ skipHtmlTags: ['script','noscript','style','textarea','pre'] }}
}};
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: "Segoe UI", system-ui, sans-serif;
  background: #f1f5f9; color: #1e293b;
  line-height: 1.65; padding: 2rem 1rem 8rem;
}}
.container {{ max-width: 900px; margin: 0 auto; }}
h1 {{ font-size: 1.5rem; margin-bottom: .25rem; color: #0f172a; }}
.subtitle {{ color: #64748b; font-size: .9rem; margin-bottom: 2rem; }}
.stats {{ display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:2rem; }}
.stat {{ background:#fff; border:1px solid #e2e8f0; border-radius:8px;
         padding:.6rem 1rem; font-size:.85rem; color:#475569; }}
.stat strong {{ color:#0f172a; display:block; font-size:1.1rem; }}

/* Questão card */
.question {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 1.25rem 1.5rem; margin-bottom: 1.25rem;
  box-shadow: 0 1px 3px rgba(0,0,0,.04);
  transition: box-shadow .15s, border-color .15s;
}}
.question.selected {{
  border-color: #6366f1;
  box-shadow: 0 0 0 3px #6366f120;
}}
.question.error-item {{ border-left: 4px solid #ef4444; }}
.question.is-subitem {{
  margin-left: 2rem;
  border-left: 3px solid #bfdbfe;
}}

/* Header */
.q-header {{
  display: flex; align-items: center; gap: .45rem;
  flex-wrap: wrap; margin-bottom: 1rem;
}}
.q-fonte {{ margin-left: auto; font-size: .78rem; color: #94a3b8; }}
.badge {{
  font-size: .7rem; font-weight: 700; border-radius: 999px;
  padding: .15rem .55rem; white-space: nowrap;
}}

/* Header inputs */
.header-input, .header-select {{
  border: 1px solid transparent; border-radius: 4px;
  padding: .15rem .3rem; font-size: .85rem; font-weight: 600;
  background: transparent; color: inherit;
  transition: border-color .15s, background .15s;
}}
.header-input:hover, .header-select:hover {{ border-color: #cbd5e1; background: #f8fafc; }}
.header-input:focus, .header-select:focus {{
  outline: none; border-color: #6366f1; background: #fff;
}}
.header-label {{ font-size: .8rem; color: #94a3b8; }}
.mc-resp-input {{ width: 2.5rem; text-align: center; text-transform: uppercase; font-weight: 700; color: #6366f1; }}
.header-save-btn {{
  background: #6366f1; color: #fff; border: none;
  border-radius: 5px; padding: .2rem .6rem; font-size: .8rem;
  cursor: pointer;
}}
.header-save-btn:hover {{ background: #4f46e5; }}
.approve-btn {{
  background: #22c55e; color: #fff; border: none;
  border-radius: 6px; padding: .2rem .6rem; font-size: .8rem;
  font-weight: 600; cursor: pointer;
}}
.approve-btn:hover {{ background: #16a34a; }}
.approve-btn:disabled {{ background: #94a3b8; cursor: not-allowed; }}

/* Body */
.q-body {{ display: flex; flex-direction: column; gap: .9rem; }}
.field-block {{ display: flex; flex-direction: column; gap: .35rem; }}
.field-label {{
  font-size: .75rem; font-weight: 700; color: #94a3b8;
  letter-spacing: .04em; text-transform: uppercase;
  display: flex; align-items: center; gap: .4rem;
}}
.field-text p {{ margin-bottom: .6rem; }}
.field-text ul {{ margin: .4rem 0 .6rem 1.4rem; }}
.math-block {{ display: block; overflow-x: auto; margin: .6rem 0; }}

/* Edit button */
.edit-btn {{
  background: none; border: none; cursor: pointer;
  font-size: .8rem; opacity: .3; padding: 0 .15rem;
  transition: opacity .15s; flex-shrink: 0;
}}
.edit-btn:hover {{ opacity: .9; }}

/* Edit area */
.edit-area {{
  width: 100%; margin-top: .3rem; padding-top: .4rem;
  border-top: 1px dashed #cbd5e1;
}}
.edit-ta {{
  width: 100%; font-size: .82rem; font-family: monospace;
  border: 1px solid #94a3b8; border-radius: 4px;
  padding: .3rem .5rem; resize: vertical; background: #f8fafc;
}}
.edit-ta:focus {{ outline: 2px solid #6366f1; border-color: #6366f1; }}
.edit-actions {{ display: flex; gap: .5rem; margin-top: .3rem; }}
.save-btn {{
  background: #22c55e; color: #fff; border: none;
  border-radius: 5px; padding: .25rem .8rem;
  font-size: .8rem; font-weight: 600; cursor: pointer;
}}
.save-btn:hover {{ background: #16a34a; }}
.save-btn:disabled {{ background: #94a3b8; cursor: not-allowed; }}
.cancel-btn {{
  background: none; border: 1px solid #cbd5e1;
  border-radius: 5px; padding: .25rem .8rem;
  font-size: .8rem; cursor: pointer; color: #64748b;
}}
.cancel-btn:hover {{ background: #f1f5f9; }}

/* Alternativas */
.alternatives {{
  list-style: none; display: flex; flex-direction: column; gap: .45rem;
}}
.alternatives li {{
  display: flex; align-items: flex-start; gap: .5rem; flex-wrap: wrap;
  background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 8px; padding: .5rem .75rem;
}}
.alt-letter {{
  font-weight: 700; color: #6366f1; min-width: 1.2rem; padding-top: .1rem;
  flex-shrink: 0;
}}
.alt-text {{ flex: 1; min-width: 0; }}
.q-images {{ display: flex; flex-wrap: wrap; gap: .5rem; margin-top: .5rem; }}
.q-img {{
  max-width: min(560px, 100%); height: auto; border-radius: 6px;
  border: 1px solid #e2e8f0; display: block;
}}

/* Secção CC (Critérios de Classificação) */
.cc-section {{
  margin-top: .75rem; padding: 1rem 1.25rem;
  background: #f0fdf4; border: 1px solid #bbf7d0;
  border-radius: 10px;
}}
.cc-section-label {{
  font-size: .72rem; font-weight: 700; color: #16a34a;
  letter-spacing: .05em; text-transform: uppercase; margin-bottom: .6rem;
}}
.cc-resposta {{
  font-size: 1rem; padding: .5rem .75rem; margin-bottom: .75rem;
  background: #fff; border: 1px solid #bbf7d0; border-radius: 6px;
}}
.cc-letra {{ font-size: 1.2rem; color: #16a34a; }}
.cc-solucao {{
  font-size: .88rem; margin-bottom: .75rem; line-height: 1.6;
}}
.cc-solucao p {{ margin-bottom: .5rem; }}
.cc-det {{
  border: 1px solid #d1fae5; border-radius: 8px;
  overflow: hidden; margin-bottom: .5rem;
}}
.cc-det > summary {{
  padding: .5rem .8rem; font-size: .82rem; font-weight: 600;
  cursor: pointer; background: #ecfdf5; user-select: none; list-style: none;
  color: #065f46;
}}
.cc-det > summary::before {{ content: "▶ "; font-size: .65rem; }}
.cc-det[open] > summary::before {{ content: "▼ "; }}
.cc-table {{
  width: 100%; border-collapse: collapse; font-size: .82rem;
}}
.cc-table th {{
  background: #ecfdf5; padding: .35rem .65rem;
  text-align: left; font-weight: 600; color: #065f46;
}}
.cc-table td {{
  padding: .35rem .65rem; border-top: 1px solid #d1fae5;
  vertical-align: top;
}}
.pts-cell {{
  font-weight: 700; color: #16a34a; white-space: nowrap; width: 4rem;
}}
.ocr-table-wrap {{
  margin: .6rem 0; overflow-x: auto;
}}
.ocr-table-wrap table {{
  border-collapse: collapse; font-size: .88rem;
}}
.ocr-table-wrap table td,
.ocr-table-wrap table th {{
  border: 1px solid #cbd5e1; padding: .3rem .65rem;
  text-align: center; vertical-align: middle;
}}
.ocr-table-wrap table tr:first-child td,
.ocr-table-wrap table th {{
  background: #f1f5f9; font-weight: 600;
}}
.cc-alt-list {{
  list-style: none; display: flex; flex-direction: column; gap: .6rem;
  padding: .65rem .8rem;
}}
.cc-alt-list li {{ font-size: .85rem; }}

/* CC edição inline */
.cc-row-content {{
  display: flex; align-items: flex-start; gap: .4rem;
}}
.cc-row-content .cc-desc-text {{ flex: 1; white-space: pre-wrap; }}
.cc-edit-btn {{
  background: none; border: none; cursor: pointer;
  font-size: .8rem; padding: .1rem .2rem; opacity: .5; flex-shrink: 0;
  margin-left: auto;
}}
.cc-edit-btn:hover {{ opacity: 1; }}
.cc-edit-area {{ padding: .4rem 0; }}
.cc-pts-input {{
  width: 3.5rem; border: 1px solid #d1fae5; border-radius: 4px;
  padding: .2rem .4rem; font-size: .85rem; font-weight: 700; color: #16a34a;
}}
.pts-label {{ font-size: .8rem; color: #16a34a; font-weight: 600; }}
.cc-desc-ta, .cc-altres-ta {{
  width: 100%; border: 1px solid #d1fae5; border-radius: 6px;
  padding: .4rem .6rem; font-size: .82rem; resize: vertical;
  font-family: inherit; margin-top: .3rem;
}}
.cc-add-btn {{
  margin: .4rem .8rem .6rem;
  background: none; border: 1px dashed #16a34a; color: #16a34a;
  border-radius: 6px; padding: .25rem .75rem; font-size: .78rem;
  cursor: pointer;
}}
.cc-add-btn:hover {{ background: #f0fdf4; }}
.delete-btn {{
  background: none; border: none; cursor: pointer;
  font-size: .8rem; padding: .1rem .3rem; color: #ef4444;
  opacity: .6;
}}
.delete-btn:hover {{ opacity: 1; }}
.cc-solucao-block {{ background: transparent; border: none; padding: 0; margin: .5rem 0; }}
.cc-alt-item {{ position: relative; }}

/* Footer */
.q-footer {{
  border-top: 1px solid #f1f5f9; padding-top: .75rem; margin-top: .75rem;
  display: flex; flex-direction: column; gap: .35rem;
}}
.meta-item {{ font-size: .8rem; color: #64748b; }}
.descricao-breve {{ font-size: .88rem; color: #374151; font-style: italic; line-height: 1.5; }}
.tags {{ display: flex; flex-wrap: wrap; gap: .3rem; }}
.tag {{
  font-size: .72rem; background: #eff6ff; color: #3b82f6;
  border: 1px solid #bfdbfe; border-radius: 999px; padding: .1rem .5rem;
}}
.obs-det {{ border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }}
.obs-det > summary {{
  padding: .4rem .75rem; font-size: .78rem; font-weight: 600;
  cursor: pointer; background: #f8fafc; user-select: none; list-style: none;
}}
.obs-det > summary::before {{ content: "▶ "; font-size: .65rem; }}
.obs-det[open] > summary::before {{ content: "▼ "; }}
.obs-det ul {{ margin: .35rem 0 0 1rem; font-size: .78rem; color: #64748b; padding: .4rem; }}
.obs-det li {{ margin-bottom: .2rem; }}

/* Submit bar */
.submit-bar {{
  position: fixed; bottom: 0; left: 0; right: 0;
  background: #1e293b; color: #f1f5f9;
  display: flex; align-items: center; justify-content: space-between;
  padding: 1rem 2rem;
  box-shadow: 0 -2px 12px rgba(0,0,0,.2);
  z-index: 100;
}}
.selected-count {{ font-size: .9rem; opacity: .8; }}
.submit-btn {{
  background: #6366f1; color: #fff; border: none;
  border-radius: 8px; padding: .65rem 1.5rem;
  font-size: .95rem; font-weight: 600; cursor: pointer;
  transition: background .15s;
}}
.submit-btn:hover {{ background: #4f46e5; }}
.submit-btn:disabled {{ background: #475569; cursor: not-allowed; }}
.approve-upload-btn {{
  background: #16a34a; color: #fff; border: none;
  border-radius: 8px; padding: .65rem 1.5rem;
  font-size: .95rem; font-weight: 700; cursor: pointer;
  transition: background .15s; white-space: nowrap;
}}
.approve-upload-btn:hover {{ background: #15803d; }}
.approve-upload-btn.already-approved {{
  background: #374151; cursor: default; opacity: .7;
}}

/* Override badges */
.override-badge {{
  font-size: .62rem; font-weight: 700; border-radius: 999px;
  padding: .1rem .45rem; white-space: nowrap; margin-left: .25rem;
  vertical-align: middle;
}}
.override-human {{
  background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe;
}}
.override-agent {{
  background: #fff7ed; color: #ea580c; border: 1px solid #fed7aa;
}}
.alts-label {{ margin-bottom: .25rem; }}

/* Update banner */
.update-banner {{
  display: none;
  background: #fef3c7; border: 1px solid #fbbf24;
  border-radius: 8px; padding: .75rem 1.25rem; margin-bottom: 1.5rem;
  color: #92400e; font-weight: 600;
  display: flex; align-items: center; gap: .75rem;
}}
.update-banner button {{
  background: #f59e0b; color: #fff; border: none;
  border-radius: 6px; padding: .3rem .9rem; font-size: .85rem;
  font-weight: 600; cursor: pointer; white-space: nowrap;
}}
.update-banner button:hover {{ background: #d97706; }}
.stat-overlay {{ border-color: #bfdbfe; }}
</style>
</head>
<body>
<div class="container">
  <h1>{title}</h1>
  <p class="subtitle">Preview interativo — Pipeline de Exames Nacionais</p>
  {approved_banner}
  <div id="update-banner" class="update-banner" style="display:none">
    ⚠️ O agente fez alterações enquanto tinha esta página aberta.
    O que você vê pode estar desatualizado.
    <button onclick="location.reload()">🔄 Recarregar</button>
  </div>
  <div class="stats">
    <div class="stat"><strong>{total}</strong>questões</div>
    <div class="stat"><strong>{n_mc}</strong>escolha múltipla</div>
    <div class="stat"><strong>{n_or}</strong>resposta dissertativa</div>
    <div class="stat"><strong>{n_err}</strong>com erro</div>
    <div class="stat"><strong>{n_warn}</strong>com aviso</div>
    {overlay_stat_html}
  </div>
  {questions_html}
</div>

<div class="submit-bar" id="submitBar">
  <span class="selected-count" id="selectedCount">Revisão manual ativa</span>
  <div style="display:flex;gap:.75rem;align-items:center">
    <button class="approve-upload-btn{already_approved_class}" id="approveUploadBtn"
      onclick="approveForUpload()">
      {approve_label}
    </button>
  </div>
</div>

<script>
function updateCount() {{
  document.getElementById('selectedCount').textContent = 'Revisão manual ativa';
}}

function collectSelection() {{
  return [];
}}

updateCount();

// ── Helper para POST JSON (Safari-safe) ──────────────────────────────────────
function postJSON(url, body) {{
  return new Promise((resolve, reject) => {{
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onload = function() {{
      if (xhr.status === 200) {{
        try {{ resolve(JSON.parse(xhr.responseText)); }}
        catch(e) {{ reject(e); }}
      }} else {{
        reject(new Error('HTTP ' + xhr.status));
      }}
    }};
    xhr.onerror = function() {{ reject(new Error('Erro de rede')); }};
    xhr.send(JSON.stringify(body));
  }});
}}

// ── Edição do cabeçalho ───────────────────────────────────────────────────────
document.querySelectorAll('.header-input, .header-select, .mc-resp-input').forEach(el => {{
  el.addEventListener('input', function() {{
    const btn = this.closest('header').querySelector('.header-save-btn');
    if (btn) btn.style.display = '';
  }});
}});

function saveHeader(btn) {{
  const header  = btn.closest('header');
  const card    = btn.closest('.question');
  const origId  = btn.dataset.origId;
  const newId   = header.querySelector('[data-field="id_item"]').value.trim();
  const newTipo = header.querySelector('[data-field="tipo_item"]').value;
  const respEl  = header.querySelector('[data-field="resposta_correta"]');
  const newResp = respEl ? respEl.value.trim().toUpperCase() : null;

  btn.textContent = '...'; btn.disabled = true;

  postJSON('/edit-header', {{orig_id: origId, id_item: newId, tipo_item: newTipo, resposta_correta: newResp}})
  .then(data => {{
    if (data.status === 'ok') {{
      btn.style.display = 'none';
      btn.dataset.origId = newId;
      btn.textContent = '💾'; btn.disabled = false;
      header.querySelector('[data-field="id_item"]').dataset.orig = newId;
      card.dataset.id = newId;
      card.querySelectorAll('[data-item]').forEach(el => el.dataset.item = newId);
      if (data.reload) location.reload();
    }} else {{
      alert('Erro: ' + (data.error || 'desconhecido'));
      btn.textContent = '💾'; btn.disabled = false;
    }}
  }})
  .catch(err => {{ alert('Erro: ' + err); btn.textContent = '💾'; btn.disabled = false; }});
}}

// ── Aprovar questão ──────────────────────────────────────────────────────────
function approveQuestion(btn, itemId) {{
  if (!confirm('Aprovar questão ' + itemId + '?')) return;
  btn.disabled = true; btn.textContent = '...';
  postJSON('/approve', {{id_item: itemId}})
  .then(data => {{
    if (data.status === 'ok') {{
      location.reload();
    }} else {{
      alert('Erro: ' + (data.error || 'desconhecido'));
      btn.disabled = false; btn.textContent = '✅ Aprovar';
    }}
  }})
  .catch(err => {{ alert('Erro: ' + err); btn.disabled = false; btn.textContent = '✅ Aprovar'; }});
}}

// ── Edição do enunciado ───────────────────────────────────────────────────────
function toggleEdit(btn) {{
  const block    = btn.closest('.field-block');
  const editArea = block.querySelector('.edit-area');
  const fieldText = block.querySelector('.field-text');
  const isOpen   = editArea.style.display !== 'none';
  if (isOpen) {{
    editArea.style.display = 'none';
    if (fieldText) fieldText.style.display = '';
  }} else {{
    editArea.style.display = '';
    if (fieldText) fieldText.style.display = 'none';
    block.querySelector('.edit-ta').focus();
  }}
}}

function cancelEdit(btn) {{
  const block    = btn.closest('.field-block') || btn.closest('li');
  const editArea = block.querySelector('.edit-area');
  const fieldText = block.querySelector('.field-text');
  editArea.style.display = 'none';
  if (fieldText) fieldText.style.display = '';
}}

function saveEdit(btn) {{
  const block   = btn.closest('.field-block');
  const item    = btn.dataset.item;
  const field   = btn.dataset.field;
  const newText = block.querySelector('.edit-ta').value.trim();
  if (!newText) return;

  btn.disabled = true; btn.textContent = '...';

  postJSON('/edit', {{id_item: item, field: field, value: newText}})
  .then(data => {{
    if (data.status === 'ok') {{
      location.reload();
    }} else {{
      alert('Erro: ' + (data.error || 'desconhecido'));
      btn.textContent = 'Guardar'; btn.disabled = false;
    }}
  }})
  .catch(err => {{ alert('Erro: ' + err); btn.textContent = 'Guardar'; btn.disabled = false; }});
}}

// ── Edição de alternativa ─────────────────────────────────────────────────────
function toggleAltEdit(btn) {{
  const li       = btn.closest('li');
  const editArea = li.querySelector('.edit-area');
  const altText  = li.querySelector('.alt-text');
  const isOpen   = editArea.style.display !== 'none';
  if (isOpen) {{
    editArea.style.display = 'none';
    altText.style.display = '';
  }} else {{
    editArea.style.display = '';
    altText.style.display = 'none';
    li.querySelector('.edit-ta').focus();
  }}
}}

function saveAltEdit(btn) {{
  const li      = btn.closest('li');
  const item    = btn.dataset.item;
  const letra   = btn.dataset.letra;
  const newText = li.querySelector('.edit-ta').value.trim();
  if (!newText) return;

  btn.disabled = true; btn.textContent = '...';

  postJSON('/edit', {{id_item: item, field: 'alternativa', letra: letra, value: newText}})
  .then(data => {{
    if (data.status === 'ok') {{
      location.reload();
    }} else {{
      alert('Erro: ' + (data.error || 'desconhecido'));
      btn.textContent = 'Guardar'; btn.disabled = false;
    }}
  }})
  .catch(err => {{ alert('Erro: ' + err); btn.textContent = 'Guardar'; btn.disabled = false; }});
}}

// ── Edição de critérios parciais ──────────────────────────────────────────────
function toggleCcEdit(btn) {{
  const row      = btn.closest('.cc-row');
  const content  = row.querySelectorAll('.cc-row-content');
  const editArea = row.querySelectorAll('.cc-edit-area');
  const isOpen   = editArea[0].style.display !== 'none';
  content.forEach(el  => el.style.display  = isOpen ? '' : 'none');
  editArea.forEach(el => el.style.display  = isOpen ? 'none' : '');
  if (!isOpen) row.querySelector('.cc-desc-ta').focus();
}}

function cancelCcEdit(btn) {{
  const row = btn.closest('.cc-row');
  row.querySelectorAll('.cc-row-content').forEach(el => el.style.display = '');
  row.querySelectorAll('.cc-edit-area').forEach(el  => el.style.display = 'none');
}}

function saveCcEdit(btn) {{
  const row    = btn.closest('.cc-row');
  const item   = btn.dataset.item;
  const ccIdx  = parseInt(btn.dataset.ccIdx);
  const pontos = parseInt(row.querySelector('.cc-pts-input').value) || 0;
  const desc   = row.querySelector('.cc-desc-ta').value.trim();
  btn.disabled = true; btn.textContent = '...';
  postJSON('/edit-cc', {{id_item: item, cc_idx: ccIdx, action: 'edit', pontos: pontos, descricao: desc}})
  .then(data => {{
    if (data.status === 'ok') {{ location.reload(); }}
    else {{ alert('Erro: ' + (data.error || 'desconhecido')); btn.textContent = 'Guardar'; btn.disabled = false; }}
  }})
  .catch(err => {{ alert('Erro: ' + err); btn.textContent = 'Guardar'; btn.disabled = false; }});
}}

function deleteCcRow(btn) {{
  if (!confirm('Remover este critério?')) return;
  const item  = btn.dataset.item;
  const ccIdx = parseInt(btn.dataset.ccIdx);
  btn.disabled = true;
  postJSON('/edit-cc', {{id_item: item, cc_idx: ccIdx, action: 'delete'}})
  .then(data => {{
    if (data.status === 'ok') {{ location.reload(); }}
    else {{ alert('Erro: ' + (data.error || 'desconhecido')); btn.disabled = false; }}
  }})
  .catch(err => {{ alert('Erro: ' + err); btn.disabled = false; }});
}}

function addCcRow(btn) {{
  const item = btn.dataset.item;
  btn.disabled = true; btn.textContent = '...';
  postJSON('/edit-cc', {{id_item: item, action: 'add', pontos: 0, descricao: 'Novo critério'}})
  .then(data => {{
    if (data.status === 'ok') {{ location.reload(); }}
    else {{ alert('Erro: ' + (data.error || 'desconhecido')); btn.textContent = '+ Adicionar critério'; btn.disabled = false; }}
  }})
  .catch(err => {{ alert('Erro: ' + err); btn.textContent = '+ Adicionar critério'; btn.disabled = false; }});
}}

// ── Aprovar para Upload ───────────────────────────────────────────────────────
const _alreadyApproved = {already_approved_js};

function approveForUpload() {{
  if (_alreadyApproved) return;
  if (!confirm('Marcar estas questões como revistas e prontas para upload?\\n\\nApós aprovação, use run_upload() no Claude Code.')) return;
  const btn = document.getElementById('approveUploadBtn');
  btn.textContent = '...'; btn.disabled = true;
  postJSON('/approve-final', {{}})
  .then(data => {{
    if (data.status === 'ok') {{
      btn.textContent = '✅ Aprovado para Upload';
      btn.classList.add('already-approved');
      btn.disabled = false;
      const banner = document.querySelector('.approved-banner');
      if (banner) banner.style.display = '';
      alert('✅ Questões aprovadas!\\nAgora pode usar run_upload() no Claude Code.');
    }} else {{
      btn.textContent = '✅ Aprovar para Upload';
      btn.disabled = false;
      alert('Erro: ' + (data.error || 'desconhecido'));
    }}
  }})
  .catch(err => {{
    btn.textContent = '✅ Aprovar para Upload';
    btn.disabled = false;
    alert('Erro: ' + err);
  }});
}}

// ── API antiga mantida como no-op por compatibilidade ────────────────────────
function submitFallback() {{
  return;
}}

// ── Polling de versão do overlay (10 s) ──────────────────────────────────────
let _knownOverlayVersion = {initial_version_ms};

function pollOverlayVersion() {{
  fetch('/version', {{cache: 'no-store'}})
    .then(r => r.json())
    .then(data => {{
      if (data.ts !== _knownOverlayVersion) {{
        _knownOverlayVersion = data.ts;
        document.getElementById('update-banner').style.display = 'flex';
        // Desabilitar aprovação até recarregar
        const btn = document.getElementById('approveUploadBtn');
        if (btn && !btn.classList.contains('already-approved')) {{
          btn.disabled = true;
          btn.title = 'Recarregue a página para ver as alterações do agente antes de aprovar';
        }}
      }}
    }})
    .catch(() => {{}});
}}

setInterval(pollOverlayVersion, 10000);
</script>
</body>
</html>"""


# ── Construção do HTML ────────────────────────────────────────────────────────

def _build_html(
    approved_path: Path,
    rejected_path: Path | None,
    already_approved: bool = False,
    overlay_data: dict | None = None,
) -> str:
    """Constrói o HTML do preview aplicando o overlay sobre a base.

    overlay_data: resultado de overlay_mod.load_overlay(); recarregado se None.
    """
    ws_dir       = approved_path.parent
    overlay_data = overlay_data or overlay_mod.load_overlay(ws_dir)
    overlay_items = overlay_data.get("items", {})

    # Carrega questões base
    base_questions: list[Question] = load_questions(approved_path)
    if rejected_path and rejected_path.exists():
        base_questions += load_questions(rejected_path)

    # Aplica overlay: recria Question com campos sobrescritos + regista overrides por item
    questions: list[Question] = []
    questions_overrides: list[dict[str, str]] = []  # [{field: source}]
    for q in base_questions:
        item_id = q.id_item or str(q.numero_questao)
        item_overrides = overlay_items.get(item_id, {})
        if item_overrides:
            import dataclasses
            q_dict = copy.deepcopy(dataclasses.asdict(q))
            for fld, entry in item_overrides.items():
                q_dict[fld] = entry["value"]
            try:
                q = Question.from_dict(q_dict)
            except Exception:
                pass  # Se falhar, usa a questão original
        questions.append(q)
        questions_overrides.append({fld: entry["source"] for fld, entry in item_overrides.items()})

    # Timestamp do overlay para polling JS (millisegundos)
    overlay_path = ws_dir / "correcoes_humanas.json"
    initial_version_ms = int(overlay_path.stat().st_mtime * 1000) if overlay_path.exists() else 0

    def _sort_key(s: str) -> tuple:
        # Separa prefixo de grupo ("I", "II") do resto para evitar comparação str/int.
        # Usa zero-padding em números para ordenação lexicográfica correcta.
        # Ex: "II-2.1" → ("II", "002", "001"); "3" → ("", "003"); "2.1" → ("", "002", "001")
        import re as _re
        m = _re.match(r"^([IVX]+)-(.+)$", s)
        grupo_part = m.group(1) if m else ""
        rest       = m.group(2) if m else s
        parts      = rest.replace(".", " ").split()
        return (grupo_part,) + tuple(p.zfill(3) if p.isdigit() else p for p in parts)

    # Ordenar mantendo overrides associados
    paired = list(zip(questions, questions_overrides))
    paired.sort(key=lambda x: _sort_key(x[0].id_item or str(x[0].numero_questao)))

    # Deduplicar por id_item
    seen_ids: set[str] = set()
    deduped_paired: list[tuple[Question, dict]] = []
    for q, ov in paired:
        key = q.id_item or str(q.numero_questao)
        if key not in seen_ids:
            seen_ids.add(key)
            deduped_paired.append((q, ov))

    questions  = [q for q, _ in deduped_paired]
    q_overrides = [ov for _, ov in deduped_paired]

    title = (questions[0].fonte if questions else approved_path.parent.name)
    n_mc   = sum(1 for q in questions if q.tipo_item == "multiple_choice")
    n_or   = sum(1 for q in questions if q.tipo_item == "open_response")
    n_err  = sum(1 for q in questions if q.status == "error")
    n_warn = sum(1 for q in questions if "warning" in (q.status or ""))

    # Subitens: não mostrar contexto pai (o card do context_stem pai já está visível acima)
    questions_html = "\n".join(
        _render_question(q, i, show_context=(q.subitem is None), overrides=ov)
        for i, (q, ov) in enumerate(zip(questions, q_overrides), 1)
    )

    approved_banner = (
        '<div class="approved-banner" style="background:#dcfce7;border:1px solid #86efac;'
        'border-radius:8px;padding:.75rem 1.25rem;margin-bottom:1.5rem;color:#166534;font-weight:600;">'
        '✅ Questões aprovadas para upload — pode usar run_upload() no Claude Code.</div>'
        if already_approved else
        '<div class="approved-banner" style="display:none;background:#dcfce7;border:1px solid #86efac;'
        'border-radius:8px;padding:.75rem 1.25rem;margin-bottom:1.5rem;color:#166534;font-weight:600;">'
        '✅ Questões aprovadas para upload — pode usar run_upload() no Claude Code.</div>'
    )
    # Estatísticas do overlay para o rodapé informativo
    has_overlay      = bool(overlay_items)
    n_overridden     = len(overlay_items)
    overlay_stat_html = (
        f'<div class="stat stat-overlay"><strong>{n_overridden}</strong>com correcções</div>'
        if has_overlay else ""
    )

    return _HTML_TEMPLATE.format(
        title=html.escape(title),
        total=len(questions),
        n_mc=n_mc,
        n_or=n_or,
        n_err=n_err,
        n_warn=n_warn,
        questions_html=questions_html,
        approved_banner=approved_banner,
        already_approved_js="true" if already_approved else "false",
        already_approved_class=" already-approved" if already_approved else "",
        approve_label="✅ Aprovado para Upload" if already_approved else "✅ Aprovar para Upload",
        initial_version_ms=initial_version_ms,
        overlay_stat_html=overlay_stat_html,
    )


# ── Servidor HTTP ─────────────────────────────────────────────────────────────

def _make_handler(
    approved_path: Path,
    rejected_path: Path | None,
    output_path: Path,
    done: threading.Event,
    review_approved_path: Path | None = None,
    ws_dir: Path | None = None,
):
    _review_approved_path = review_approved_path or (approved_path.parent / ".review_approved")
    _ws_dir = ws_dir or approved_path.parent

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                # Recarrega overlay do disco a cada request (pode ter sido alterado pelo agente)
                current_overlay = overlay_mod.load_overlay(_ws_dir)
                body = _build_html(
                    approved_path, rejected_path,
                    _review_approved_path.exists(),
                    overlay_data=current_overlay,
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()
            elif self.path == "/version":
                self._handle_version()
            elif self.path.startswith("/imagens_extraidas/") or self.path.startswith("/images/"):
                img_rel  = self.path.lstrip("/")
                img_path = approved_path.parent / img_rel
                if img_path.exists() and img_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                    data = img_path.read_bytes()
                    ct = "image/jpeg" if img_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
                    self.send_response(200)
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_response(404)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def _send_json(self, data: dict) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def _handle_version(self) -> None:
            """Devolve o mtime do overlay em ms (para polling JS)."""
            overlay_path = _ws_dir / "correcoes_humanas.json"
            ts = int(overlay_path.stat().st_mtime * 1000) if overlay_path.exists() else 0
            body = json.dumps({"ts": ts}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def do_OPTIONS(self):
            """Handle CORS preflight for Safari."""
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.flush()

        def do_POST(self):
            try:
                length  = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))

                if self.path == "/submit":
                    output_path.write_text(
                        json.dumps(payload, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    self._send_json({"status": "ok"})

                elif self.path == "/approve":
                    self._handle_approve(payload)

                elif self.path == "/approve-final":
                    self._handle_approve_final()

                elif self.path == "/edit":
                    self._handle_edit(payload)

                elif self.path == "/edit-header":
                    self._handle_edit_header(payload)

                elif self.path == "/edit-cc":
                    self._handle_edit_cc(payload)

                else:
                    self.send_response(404)
                    self.end_headers()
            except Exception as exc:
                import traceback
                traceback.print_exc()
                try:
                    self._send_json({"status": "error", "error": str(exc)})
                except Exception:
                    pass

        def _find_question(self, item_id: str) -> tuple[Path, list[dict], int] | None:
            """Procura item_id em aprovadas e depois em rejeitadas. Retorna (path, lista, index)."""
            for path in [approved_path, rejected_path]:
                if path is None or not path.exists():
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                for i, q in enumerate(data):
                    if str(q.get("id_item", "")) == item_id:
                        return path, data, i
            return None

        def _handle_approve_final(self) -> None:
            try:
                # Materializar estado actual (base + overlay) e salvar como snapshot aprovado
                current_ov = overlay_mod.load_overlay(_ws_dir)
                base_path  = approved_path  # questoes_final.json ou questoes_aprovadas.json
                base_data  = json.loads(base_path.read_text(encoding="utf-8"))
                merged, _  = overlay_mod.apply_overlay(base_data, current_ov)
                snapshot_path = _ws_dir / "questoes_final.approved_snapshot.json"
                snapshot_path.write_text(
                    json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                _review_approved_path.touch()
                self._send_json({"status": "ok"})
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

        def _handle_approve(self, payload: dict) -> None:
            item_id = str(payload.get("id_item", ""))
            try:
                if rejected_path is None or not rejected_path.exists():
                    self._send_json({"status": "error", "error": "sem ficheiro de erros"})
                    return
                erros = json.loads(rejected_path.read_text(encoding="utf-8"))
                found = None
                remaining = []
                for q in erros:
                    if str(q.get("id_item", "")) == item_id:
                        found = q
                    else:
                        remaining.append(q)
                if found is None:
                    self._send_json({"status": "error", "error": "item não encontrado nos erros"})
                    return
                found["status"] = "approved"
                # Adiciona a aprovadas
                aprovadas = json.loads(approved_path.read_text(encoding="utf-8"))
                aprovadas.append(found)
                approved_path.write_text(
                    json.dumps(aprovadas, indent=2, ensure_ascii=False), encoding="utf-8")
                rejected_path.write_text(
                    json.dumps(remaining, indent=2, ensure_ascii=False), encoding="utf-8")
                self._send_json({"status": "ok"})
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

        def _handle_edit(self, payload: dict) -> None:
            item_id = str(payload.get("id_item", ""))
            field   = payload.get("field", "")
            value   = str(payload.get("value", "")).strip()

            SIMPLE_FIELDS = {"enunciado", "solucao", "resposta_correta", "enunciado_contexto_pai"}

            try:
                if field in SIMPLE_FIELDS:
                    if self._find_question(item_id) is None:
                        self._send_json({"status": "error", "error": "item não encontrado"})
                        return
                    overlay_mod.set_override(_ws_dir, item_id, field, value, source="human")

                elif field == "alternativa":
                    result = self._find_question(item_id)
                    if result is None:
                        self._send_json({"status": "error", "error": "item não encontrado"})
                        return
                    _, base_list, base_idx = result
                    letra = payload.get("letra", "")
                    # Obter alternativas efectivas (overlay > base)
                    current_ov = overlay_mod.load_overlay(_ws_dir)
                    eff_alts   = overlay_mod.get_effective_field(
                        base_list, current_ov, item_id, "alternativas", default=None,
                    )
                    if eff_alts is None:
                        eff_alts = base_list[base_idx].get("alternativas", [])
                    eff_alts = copy.deepcopy(eff_alts or [])
                    for alt in eff_alts:
                        if alt.get("letra") == letra:
                            alt["texto"] = value
                            break
                    overlay_mod.set_override(_ws_dir, item_id, "alternativas", eff_alts, source="human")

                else:
                    self._send_json({"status": "error", "error": f"campo desconhecido: {field}"})
                    return

                self._send_json({"status": "ok"})
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

        def _handle_edit_cc(self, payload: dict) -> None:
            item_id = str(payload.get("id_item", ""))
            action  = payload.get("action", "edit")
            try:
                result = self._find_question(item_id)
                if result is None:
                    self._send_json({"status": "error", "error": "item não encontrado"})
                    return
                _, base_list, base_idx = result
                # Obter criterios_parciais efectivos (overlay > base)
                current_ov = overlay_mod.load_overlay(_ws_dir)
                eff_criterios = overlay_mod.get_effective_field(
                    base_list, current_ov, item_id, "criterios_parciais", default=None,
                )
                if eff_criterios is None:
                    eff_criterios = base_list[base_idx].get("criterios_parciais", [])
                criterios = copy.deepcopy(eff_criterios or [])

                if action == "edit":
                    cc_idx = int(payload.get("cc_idx", -1))
                    if cc_idx < 0 or cc_idx >= len(criterios):
                        self._send_json({"status": "error", "error": "índice inválido"})
                        return
                    criterios[cc_idx]["pontos"]    = payload.get("pontos", criterios[cc_idx].get("pontos", 0))
                    criterios[cc_idx]["descricao"] = payload.get("descricao", "").strip()
                elif action == "delete":
                    cc_idx = int(payload.get("cc_idx", -1))
                    if cc_idx < 0 or cc_idx >= len(criterios):
                        self._send_json({"status": "error", "error": "índice inválido"})
                        return
                    criterios.pop(cc_idx)
                elif action == "add":
                    criterios.append({
                        "pontos":    payload.get("pontos", 0),
                        "descricao": payload.get("descricao", "").strip(),
                    })
                else:
                    self._send_json({"status": "error", "error": f"acção desconhecida: {action}"})
                    return

                overlay_mod.set_override(_ws_dir, item_id, "criterios_parciais", criterios, source="human")
                self._send_json({"status": "ok"})
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

        def _handle_edit_header(self, payload: dict) -> None:
            orig_id  = str(payload.get("orig_id", ""))
            new_id   = payload.get("id_item", orig_id).strip()
            new_tipo = payload.get("tipo_item", "open_response")
            new_resp = (payload.get("resposta_correta") or "").strip().upper() or None
            try:
                result = self._find_question(orig_id)
                if result is None:
                    self._send_json({"status": "error", "error": "item não encontrado"})
                    return
                path, data, idx = result
                tipo_changed = data[idx].get("tipo_item") != new_tipo
                data[idx]["id_item"]          = new_id
                data[idx]["tipo_item"]         = new_tipo
                data[idx]["resposta_correta"]  = new_resp if new_tipo == "multiple_choice" else None
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                self._send_json({"status": "ok", "reload": tipo_changed})
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

        def log_message(self, fmt, *args):
            # Só loga erros (status >= 400)
            if args and str(args[0]).startswith(("4", "5")):
                import sys
                print(f"[preview] {self.path} → {args[0]}", file=sys.stderr)

        def log_error(self, fmt, *args):
            import sys
            print(f"[preview] ERROR: {fmt % args}", file=sys.stderr)

    return _Handler


# ── Ponto de entrada ───────────────────────────────────────────────────────────

def run_preview(
    approved_path: Path,
    output_path: Path | None = None,
    port: int = _DEFAULT_PORT,
    review_approved_path: Path | None = None,
) -> Path:
    """
    Abre o preview interativo das questões no browser.

    Mantém o servidor vivo até Ctrl+C.
    Escreve questoes_revisao.json quando o utilizador submete.
    O botão "Aprovar para Upload" cria .review_approved no workspace.
    Retorna o caminho de questoes_revisao.json.
    """
    approved_path = approved_path.resolve()
    rejected_path = approved_path.parent / "questoes_com_erro.json"
    if not rejected_path.exists():
        rejected_path = None

    if output_path is None:
        output_path = approved_path.parent / "questoes_revisao.json"

    if review_approved_path is None:
        review_approved_path = approved_path.parent / ".review_approved"

    done = threading.Event()
    handler_class = _make_handler(
        approved_path, rejected_path, output_path, done,
        review_approved_path,
        ws_dir=approved_path.parent,
    )

    class _ReuseServer(socketserver.TCPServer):
        allow_reuse_address = True

    with _ReuseServer(("localhost", port), handler_class) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()

        url = f"http://localhost:{port}"
        print(f"[preview] A abrir {url}")
        print("[preview] Edite e reveja as questões antes da aprovação final.")
        print("[preview] Prima Ctrl+C para fechar o servidor quando terminar.")
        webbrowser.open(url)

        try:
            done.wait()
        except KeyboardInterrupt:
            print("\n[preview] Encerrado pelo utilizador.")
        finally:
            httpd.shutdown()

    print(f"[preview] ✅ {output_path}")
    return output_path
