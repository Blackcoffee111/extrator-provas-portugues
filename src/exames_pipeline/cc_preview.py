"""
Módulo CC-Preview — Preview interativo dos critérios de classificação.

Abre um servidor HTTP local e exibe um HTML com todos os critérios.
O utilizador pode seleccionar itens para fallback multimodal e clicar
"Enviar para revisão" — o servidor escreve revisao.json e termina.
"""
from __future__ import annotations

import functools
import html
import http.server
import json
import re
import threading
import webbrowser
from pathlib import Path

from .schemas import CriterioRaw, load_criterios

_DEFAULT_PORT = 8799

# ── Conversão Markdown/LaTeX → HTML ──────────────────────────────────────────

_BLOCK_MATH_RE  = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\$(?!\$)(.+?)\$", re.DOTALL)
_BOLD_RE        = re.compile(r"\*\*(.+?)\*\*")
_BULLET_RE      = re.compile(r"(?m)^[•\-]\s+(.+)$")


def _md_to_html(text: str) -> str:
    """Converte Markdown/LaTeX simples para HTML com placeholders de math."""
    block_math: list[str] = []
    inline_math: list[str] = []

    def save_block(m: re.Match) -> str:
        block_math.append(m.group(0))
        return f"\x00BM{len(block_math)-1}\x00"

    def save_inline(m: re.Match) -> str:
        inline_math.append(m.group(0))
        return f"\x00IM{len(inline_math)-1}\x00"

    text = _BLOCK_MATH_RE.sub(save_block, text)
    text = _INLINE_MATH_RE.sub(save_inline, text)
    text = html.escape(text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _BULLET_RE.sub(r"<li>\1</li>", text)
    text = re.sub(r"(<li>.*?</li>)+", lambda m: f"<ul>{m.group(0)}</ul>", text, flags=re.DOTALL)

    paragraphs = re.split(r"\n{2,}", text.strip())
    parts: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith(("<ul>", "\x00BM")):
            parts.append(p)
        else:
            parts.append(f"<p>{p.replace(chr(10), '<br>')}</p>")
    text = "\n".join(parts)

    for i, m in enumerate(block_math):
        text = text.replace(f"\x00BM{i}\x00",
                            f'<span class="math-block">\\[{m[2:-2]}\\]</span>')
    for i, m in enumerate(inline_math):
        text = text.replace(f"\x00IM{i}\x00", f'\\({m[1:-1]}\\)')
    return text


# ── Renderização de cada critério ─────────────────────────────────────────────

def _tipo_badge(tipo: str) -> str:
    if tipo == "multiple_choice":
        return '<span class="badge badge-mc">EM</span>'
    if tipo == "open_response":
        return '<span class="badge badge-or">RD</span>'
    return f'<span class="badge badge-unk">{html.escape(tipo)}</span>'


def _status_badge(status: str) -> str:
    colours = {
        "approved":                ("✅", "#22c55e"),
        "approved_with_warnings":  ("⚠️",  "#f59e0b"),
        "approved_after_fallback": ("🔁", "#6366f1"),
        "error":                   ("❌", "#ef4444"),
        "pending_review":          ("⏳", "#94a3b8"),
        "parsed":                  ("🔍", "#64748b"),
    }
    emoji, colour = colours.get(status, ("?", "#94a3b8"))
    label = status.replace("_", " ")
    return (f'<span class="badge" style="background:{colour}20;color:{colour};'
            f'border:1px solid {colour}60">{emoji} {label}</span>')


def _render_criterio(c: CriterioRaw, index: int) -> str:
    item_id  = html.escape(c.id_item)
    fonte    = html.escape(c.fonte or "")
    tipo_val = html.escape(c.tipo)
    resposta = html.escape(c.resposta_correta or "")

    # Cabeçalho com edição inline de id_item, tipo e resposta_correta
    mc_answer_field = ""
    if c.tipo == "multiple_choice":
        mc_answer_field = (
            f' <span class="header-label">Opção</span>'
            f'<input class="header-input mc-resp-input" size="2" maxlength="1"'
            f' value="{resposta}" data-field="resposta_correta"'
            f' placeholder="A-D" title="Resposta correcta (A/B/C/D)">'
        )

    header = f"""
  <header class="cc-header">
    <span class="header-label">#</span>
    <input class="header-input id-input" size="4" value="{item_id}"
      data-field="id_item" title="Editar id do item" data-orig="{item_id}">
    <select class="header-select tipo-select" data-field="tipo" title="Tipo">
      <option value="multiple_choice"{'selected' if c.tipo=='multiple_choice' else ''}>EM</option>
      <option value="open_response"{'selected' if c.tipo=='open_response' else ''}>RD</option>
    </select>
    {_status_badge(c.status)}
    <span class="pontos">{c.cotacao_total} pts</span>
    {mc_answer_field}
    <button class="header-save-btn" onclick="saveHeader(this)"
      data-orig-id="{item_id}" style="display:none">💾</button>
    {'<button class="approve-btn" onclick="approveItem(this)" data-item-id="' + item_id + '" title="Aprovar este item sem fallback">✅ Aprovar</button>' if c.status == 'error' else ''}
    <span class="fonte">{fonte}</span>
  </header>"""

    body = ""

    if c.tipo == "multiple_choice":
        letra = html.escape(c.resposta_correta or "?")
        cb = (f'<label class="bullet-cb-wrap" title="Marcar para revisão" onclick="setTimeout(updateCount,0)">'
              f'<input type="checkbox" class="bullet-cb" '
              f'data-item="{item_id}" data-idx="0"><span class="cb-icon">🔁</span></label>')
        body = f'<div class="mc-answer">{cb} Resposta correta: <strong class="mc-letter">{letra}</strong></div>'

    else:
        # ── Contexto introdutório (texto antes do 1.º Processo) ──────────────
        if c.contexto:
            body += f'<div class="contexto-intro">{_md_to_html(c.contexto)}</div>'

        if c.criterios_parciais:
            items_html = ""
            for bi, cp in enumerate(c.criterios_parciais):
                pts      = html.escape(str(cp.get("pontos", "?")))
                desc_raw = str(cp.get("descricao", ""))
                desc     = _md_to_html(desc_raw)
                desc_esc = html.escape(desc_raw)
                cb = (f'<label class="bullet-cb-wrap" title="Marcar este bullet para revisão" onclick="setTimeout(updateCount,0)">'
                      f'<input type="checkbox" class="bullet-cb" '
                      f'data-item="{item_id}" data-idx="{bi}"><span class="cb-icon">🔁</span></label>')
                edit_btn = (f'<button class="edit-btn" title="Editar manualmente" '
                            f'onclick="toggleEdit(this)" '
                            f'data-item="{item_id}" data-idx="{bi}">✏️</button>')
                edit_area = (f'<div class="edit-area" style="display:none">'
                             f'<textarea class="edit-ta" rows="3">{desc_esc}</textarea>'
                             f'<div class="edit-actions">'
                             f'<button class="save-btn" onclick="saveEdit(this)" '
                             f'data-item="{item_id}" data-idx="{bi}">Guardar</button>'
                             f'<button class="cancel-btn" onclick="cancelEdit(this)">Cancelar</button>'
                             f'</div></div>')
                items_html += (f'<li data-item="{item_id}" data-idx="{bi}">'
                               f'{cb}<span class="cp-pts">{pts} pts</span>'
                               f'<span class="desc-text">{desc}</span>'
                               f'{edit_btn}{edit_area}</li>')
            body += f'<ul class="criterios-list">{items_html}</ul>'
        else:
            raw = c.solucao or c.texto_original or "_Sem critérios_"
            formatted = re.sub(r'(\d+\s+pont[oa]s?)', r'\1\n', raw)
            raw_esc = html.escape(raw)
            cb = (f'<label class="bullet-cb-wrap" title="Marcar para revisão" onclick="setTimeout(updateCount,0)">'
                  f'<input type="checkbox" class="bullet-cb" '
                  f'data-item="{item_id}" data-idx="0"><span class="cb-icon">🔁</span></label>')
            edit_btn = (f'<button class="edit-btn" title="Editar texto da solução" '
                        f'onclick="toggleEdit(this)" '
                        f'data-item="{item_id}" data-idx="-1">✏️</button>')
            edit_area = (f'<div class="edit-area" style="display:none">'
                         f'<textarea class="edit-ta" rows="6">{raw_esc}</textarea>'
                         f'<div class="edit-actions">'
                         f'<button class="save-btn" onclick="saveEdit(this)" '
                         f'data-item="{item_id}" data-idx="-1">Guardar</button>'
                         f'<button class="cancel-btn" onclick="cancelEdit(this)">Cancelar</button>'
                         f'</div></div>')
            body += (f'<div class="solucao pending">'
                     f'<div class="solucao-edit-wrapper">'
                     f'<div class="solucao-toolbar">{cb}{edit_btn}</div>'
                     f'<span class="desc-text">{_md_to_html(formatted)}</span>'
                     f'{edit_area}'
                     f'</div>'
                     f'</div>')

        # ── Imagens referenciadas no bloco ────────────────────────────────────
        if c.imagens:
            imgs_html = "".join(
                f'<figure class="cc-figure">'
                f'<img src="/{html.escape(p)}" alt="{html.escape(p)}" loading="lazy">'
                f'<figcaption>{html.escape(p.split("/")[-1])}</figcaption>'
                f'</figure>'
                for p in c.imagens
            )
            body += f'<div class="cc-figures">{imgs_html}</div>'

        if c.resolucoes_alternativas:
            alts = ""
            for i, alt in enumerate(c.resolucoes_alternativas, 2):
                alts += f"<li><strong>{i}.º Processo</strong><br>{_md_to_html(alt)}</li>"
            body += f"""
        <details class="alt-det">
          <summary>Processos alternativos ({len(c.resolucoes_alternativas)})</summary>
          <ol class="alt-list">{alts}</ol>
        </details>"""

    obs_html = ""
    if c.observacoes:
        lis = "".join(f"<li>{html.escape(o)}</li>" for o in c.observacoes)
        obs_html = f'<details class="obs-det"><summary>Observações ({len(c.observacoes)})</summary><ul>{lis}</ul></details>'

    return f"""
<article class="criterio" id="cc-{index}" data-id="{item_id}">
  {header}
  <div class="cc-body">
    {body}
    {obs_html}
  </div>
</article>"""


def _render_missing(item_id: str, cotacao: int, index: int) -> str:
    """Card para itens presentes na cotacoes_estrutura mas ausentes do CC-VD."""
    eid = html.escape(item_id)
    return f"""
<article class="criterio missing" id="cc-{index}" data-id="{eid}">
  <header class="cc-header">
    <span class="item-num">#{eid}</span>
    <span class="badge badge-unk">ausente CC</span>
    <span class="pontos">{cotacao} pts</span>
  </header>
  <div class="cc-body">
    <div class="solucao pending">⚠️ Este item não tem critérios no CC-VD (cotação: {cotacao} pts).</div>
  </div>
</article>"""


# ── Template HTML ──────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Revisão CC</title>
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

/* Critério card */
.criterio {{
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 1.25rem 1.5rem; margin-bottom: 1.25rem;
  box-shadow: 0 1px 3px rgba(0,0,0,.04);
  transition: box-shadow .15s, border-color .15s;
}}
.criterio.selected {{
  border-color: #6366f1;
  box-shadow: 0 0 0 3px #6366f120;
}}
.cc-header {{
  display: flex; align-items: center; gap: .5rem;
  flex-wrap: wrap; margin-bottom: 1rem;
}}
.cb-wrap {{
  display: flex; align-items: center; cursor: pointer;
  padding: .3rem .5rem; border-radius: 6px;
  border: 1px solid #e2e8f0; background: #f8fafc;
  transition: background .1s, border-color .1s;
  user-select: none;
}}
.cb-wrap:hover {{ background: #ede9fe; border-color: #a5b4fc; }}
input[type=checkbox] {{ display: none; }}
.cb-icon {{ font-size: .9rem; opacity: .5; transition: opacity .1s; }}
input:checked + .cb-icon {{ opacity: 1; }}
.item-num {{
  font-weight: 700; font-size: 1.05rem;
  background: #f1f5f9; border-radius: 6px;
  padding: .2rem .65rem; color: #334155;
}}
.pontos {{
  margin-left: auto; font-size: .82rem; font-weight: 600;
  color: #0f172a; background: #f1f5f9;
  border-radius: 6px; padding: .2rem .5rem;
}}
.fonte {{ font-size: .75rem; color: #94a3b8; }}
.badge {{
  font-size: .7rem; font-weight: 700; border-radius: 999px;
  padding: .15rem .55rem; white-space: nowrap;
}}
.badge-mc {{ background: #ede9fe; color: #6d28d9; border: 1px solid #c4b5fd; }}
.badge-or {{ background: #e0f2fe; color: #0369a1; border: 1px solid #7dd3fc; }}
.badge-unk {{ background: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }}

/* Body */
.cc-body {{ display: flex; flex-direction: column; gap: .75rem; }}
.mc-answer {{
  font-size: 1.1rem; padding: .75rem 1rem;
  background: #f0fdf4; border: 1px solid #bbf7d0;
  border-radius: 8px;
}}
.mc-letter {{ font-size: 1.4rem; color: #16a34a; }}

.solucao {{ font-size: .92rem; }}
.solucao p {{ margin-bottom: .6rem; }}
.solucao.pending {{ background: #fefce8; border-left: 3px solid #f59e0b; padding: .6rem .9rem; border-radius: 6px; }}
.solucao-toolbar {{ display: flex; align-items: center; gap: .4rem; margin-bottom: .4rem; }}
.solucao-edit-wrapper .edit-area {{ margin-top: .5rem; }}

.criterios-list {{
  list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column; gap: .45rem;
}}
.criterios-list li {{
  display: flex; gap: .55rem; align-items: baseline;
  padding: .4rem .6rem; border-radius: 6px; background: #f8fafc;
  border-left: 3px solid #cbd5e1; font-size: .88rem;
  transition: background .1s;
}}
.criterios-list li:hover {{ background: #f1f5f9; }}
.criterios-list li.bullet-selected {{
  background: #ede9fe; border-left-color: #6366f1;
}}
.cp-pts {{
  min-width: 3.5rem; text-align: right; font-weight: 700;
  color: #3b82f6; white-space: nowrap; flex-shrink: 0;
}}

/* Checkbox por bullet */
.bullet-cb-wrap {{
  display: inline-flex; align-items: center; cursor: pointer;
  flex-shrink: 0; margin-right: .2rem;
}}
.bullet-cb-wrap input[type=checkbox] {{ display: none; }}
.bullet-cb-wrap .cb-icon {{ font-size: .85rem; opacity: .35; transition: opacity .15s; }}
.bullet-cb-wrap input:checked + .cb-icon {{ opacity: 1; }}
.bullet-cb-wrap:hover .cb-icon {{ opacity: .7; }}

/* Edição do cabeçalho */
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
  cursor: pointer; margin-left: .3rem;
}}
.header-save-btn:hover {{ background: #4f46e5; }}

/* Itens ausentes / erro */
.criterio.missing {{ opacity: .65; border: 2px dashed #cbd5e1; }}
.criterio.error-item {{ border-left: 4px solid #ef4444; }}
.approve-btn {{
  background: #22c55e; color: #fff; border: none;
  border-radius: 5px; padding: .2rem .7rem; font-size: .8rem;
  cursor: pointer; margin-left: .5rem;
}}
.approve-btn:hover {{ background: #16a34a; }}
.approve-btn:disabled {{ opacity: .5; cursor: default; }}

/* Edição manual */
.edit-btn {{
  margin-left: auto; flex-shrink: 0;
  background: none; border: none; cursor: pointer;
  font-size: .8rem; opacity: .3; padding: 0 .2rem;
  transition: opacity .15s;
}}
.edit-btn:hover {{ opacity: .9; }}
.criterios-list li {{ flex-wrap: wrap; }}
.desc-text {{ flex: 1; min-width: 0; }}
.edit-area {{
  width: 100%; margin-top: .5rem; padding: .4rem .2rem;
  border-top: 1px dashed #cbd5e1;
}}
.edit-ta {{
  width: 100%; font-size: .82rem; font-family: monospace;
  border: 1px solid #94a3b8; border-radius: 4px;
  padding: .3rem .5rem; resize: vertical;
  background: #f8fafc;
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
li.edited {{ border-left-color: #22c55e; background: #f0fdf4; }}
.math-block {{ display: block; overflow-x: auto; margin: .6rem 0; }}

.criterios-det, .alt-det, .obs-det {{
  border: 1px solid #e2e8f0; border-radius: 8px;
  overflow: hidden;
}}
.criterios-det > summary,
.alt-det > summary,
.obs-det > summary {{
  padding: .55rem .85rem; font-size: .82rem; font-weight: 600;
  cursor: pointer; background: #f8fafc; user-select: none;
  list-style: none;
}}
.criterios-det > summary::before {{ content: "▶ "; font-size: .65rem; }}
.criterios-det[open] > summary::before {{ content: "▼ "; }}
.alt-det > summary::before {{ content: "▶ "; font-size: .65rem; }}
.alt-det[open] > summary::before {{ content: "▼ "; }}
.obs-det > summary::before {{ content: "▶ "; font-size: .65rem; }}
.obs-det[open] > summary::before {{ content: "▼ "; }}

.criterios-table {{
  width: 100%; border-collapse: collapse; font-size: .85rem;
}}
.criterios-table th {{
  background: #f1f5f9; padding: .4rem .75rem;
  text-align: left; font-weight: 600; color: #475569;
}}
.criterios-table td {{
  padding: .4rem .75rem; border-top: 1px solid #f1f5f9;
  vertical-align: top;
}}
.pts-cell {{
  font-weight: 700; color: #6366f1; white-space: nowrap; width: 3.5rem;
}}
.alt-list {{
  list-style: none; display: flex; flex-direction: column; gap: .75rem;
  padding: .75rem .85rem;
}}
.obs-det ul {{ margin: .4rem 0 0 1rem; font-size: .78rem; color: #64748b; padding: .5rem; }}
.obs-det li {{ margin-bottom: .2rem; }}

/* Contexto introdutório */
.contexto-intro {{
  background: #f0f9ff; border-left: 3px solid #38bdf8;
  border-radius: 0 6px 6px 0; padding: .55rem .85rem;
  margin-bottom: .75rem; font-size: .85rem; color: #0369a1;
}}

/* Figuras / imagens do bloco */
.cc-figures {{
  display: flex; flex-wrap: wrap; gap: .75rem;
  margin-top: .75rem; padding-top: .65rem;
  border-top: 1px dashed #e2e8f0;
}}
.cc-figure {{
  margin: 0; display: flex; flex-direction: column; align-items: flex-start; gap: .25rem;
}}
.cc-figure img {{
  max-width: min(560px, 100%); border: 1px solid #e2e8f0;
  border-radius: 6px; background: #f8fafc;
}}
.cc-figure figcaption {{
  font-size: .7rem; color: #94a3b8; font-family: monospace;
}}

/* Barra de submissão sticky */
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
.success-msg {{ color: #4ade80; font-weight: 600; font-size: .95rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>Revisão — Critérios de Classificação</h1>
  <p class="subtitle">{title}</p>
  <div class="stats">
    <div class="stat"><strong>{total}</strong>itens</div>
    <div class="stat"><strong>{n_mc}</strong>escolha múltipla</div>
    <div class="stat"><strong>{n_or}</strong>resposta aberta</div>
    <div class="stat"><strong>{n_warn}</strong>com avisos</div>
    <div class="stat"><strong>{n_err}</strong>com erro</div>
  </div>
  {criterios_html}
</div>

<div class="submit-bar" id="submitBar">
  <span class="selected-count" id="selectedCount">0 bullets selecionados para revisão</span>
  <button class="submit-btn" id="submitBtn" onclick="submitFallback()" disabled>
    Enviar para fallback
  </button>
</div>

<script>
// Formato revisao.json: {{item_id: [bullet_idx, ...], ...}}
function collectSelection() {{
  const sel = {{}};
  document.querySelectorAll('.bullet-cb:checked').forEach(cb => {{
    const item = cb.dataset.item;
    const idx  = parseInt(cb.dataset.idx, 10);
    if (!sel[item]) sel[item] = [];
    sel[item].push(idx);
  }});
  return sel;
}}

function updateCount() {{
  const n = document.querySelectorAll('.bullet-cb:checked').length;
  document.getElementById('selectedCount').textContent =
    n === 0 ? '0 bullets selecionados para revisão'
            : n + (n === 1 ? ' bullet selecionado' : ' bullets selecionados') + ' para revisão';
  document.getElementById('submitBtn').disabled = (n === 0);
}}

document.querySelectorAll('.bullet-cb').forEach(cb => {{
  cb.addEventListener('change', function() {{
    const li = this.closest('li');
    if (li) li.classList.toggle('bullet-selected', this.checked);
    // Highlight do card pai
    const card = this.closest('.criterio');
    if (card) {{
      const anyChecked = card.querySelectorAll('.bullet-cb:checked').length > 0;
      card.classList.toggle('selected', anyChecked);
    }}
    updateCount();
  }});
}});

updateCount();

// ── Edição do cabeçalho (id_item, tipo, resposta_correta) ─────────────────────
document.querySelectorAll('.header-input, .header-select, .mc-resp-input').forEach(el => {{
  el.addEventListener('input', function() {{
    const btn = this.closest('header').querySelector('.header-save-btn');
    if (btn) btn.style.display = '';
  }});
}});

function saveHeader(btn) {{
  const header  = btn.closest('header');
  const card    = btn.closest('.criterio');
  const origId  = btn.dataset.origId;
  const newId   = header.querySelector('[data-field="id_item"]').value.trim();
  const newTipo = header.querySelector('[data-field="tipo"]').value;
  const respEl  = header.querySelector('[data-field="resposta_correta"]');
  const newResp = respEl ? respEl.value.trim().toUpperCase() : null;

  btn.textContent = '...'; btn.disabled = true;

  fetch('/edit-header', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{
      orig_id: origId,
      id_item: newId,
      tipo: newTipo,
      resposta_correta: newResp
    }})
  }})
  .then(r => r.json())
  .then(data => {{
    if (data.status === 'ok') {{
      btn.style.display = 'none';
      btn.dataset.origId = newId;
      btn.textContent = '💾'; btn.disabled = false;
      // Actualiza data-orig no id input e data-item nos checkboxes do card
      header.querySelector('[data-field="id_item"]').dataset.orig = newId;
      card.dataset.id = newId;
      card.querySelectorAll('[data-item]').forEach(el => el.dataset.item = newId);
      // Recarrega o tipo badge se mudou
      if (data.reload) location.reload();
    }} else {{
      alert('Erro: ' + (data.error || 'desconhecido'));
      btn.textContent = '💾'; btn.disabled = false;
    }}
  }})
  .catch(err => {{ alert('Erro: ' + err); btn.textContent = '💾'; btn.disabled = false; }});
}}

// ── Edição manual ──────────────────────────────────────────────────────────────
function _editContainer(btn) {{
  // Suporta tanto <li> (bullets normais) como .solucao-edit-wrapper (itens sem etapas)
  return btn.closest('li') || btn.closest('.solucao-edit-wrapper');
}}

function toggleEdit(btn) {{
  const el       = _editContainer(btn);
  const editArea = el.querySelector('.edit-area');
  const descText = el.querySelector('.desc-text');
  const isOpen   = editArea.style.display !== 'none';
  if (isOpen) {{
    editArea.style.display = 'none';
    if (descText) descText.style.display = '';
  }} else {{
    editArea.style.display = '';
    if (descText) descText.style.display = 'none';
    el.querySelector('.edit-ta').focus();
  }}
}}

function cancelEdit(btn) {{
  const el = _editContainer(btn);
  el.querySelector('.edit-area').style.display = 'none';
  const dt = el.querySelector('.desc-text');
  if (dt) dt.style.display = '';
}}

function saveEdit(btn) {{
  const el      = _editContainer(btn);
  const item    = btn.dataset.item;
  const idx     = parseInt(btn.dataset.idx, 10);
  const newDesc = el.querySelector('.edit-ta').value.trim();
  if (!newDesc) return;

  btn.disabled = true;
  btn.textContent = '...';

  fetch('/edit', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{item_id: item, bullet_idx: idx, descricao: newDesc}})
  }})
  .then(r => r.json())
  .then(data => {{
    if (data.status === 'ok') {{
      location.reload();
    }} else {{
      alert('Erro ao guardar: ' + (data.error || 'desconhecido'));
      btn.textContent = 'Guardar';
      btn.disabled = false;
    }}
  }})
  .catch(err => {{
    alert('Erro: ' + err);
    btn.textContent = 'Guardar';
    btn.disabled = false;
  }});
}}

function approveItem(btn) {{
  const itemId = btn.dataset.itemId;
  btn.disabled = true;
  btn.textContent = '...';
  fetch('/approve', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{item_id: itemId}})
  }})
  .then(r => r.json())
  .then(data => {{
    if (data.status === 'ok') {{
      const card = btn.closest('.criterio');
      card.classList.remove('error-item');
      const badge = card.querySelector('.badge');
      if (badge) {{ badge.textContent = '✅ approved'; badge.style.background = '#22c55e'; }}
      btn.style.display = 'none';
    }} else {{
      alert('Erro: ' + (data.error || 'desconhecido'));
      btn.disabled = false;
      btn.textContent = '✅ Aprovar';
    }}
  }})
  .catch(err => {{
    alert('Erro: ' + err);
    btn.disabled = false;
    btn.textContent = '✅ Aprovar';
  }});
}}

function submitFallback() {{
  const sel = collectSelection();
  const totalBullets = Object.values(sel).reduce((s, a) => s + a.length, 0);
  if (totalBullets === 0) return;

  document.getElementById('submitBtn').disabled = true;
  document.getElementById('submitBtn').textContent = 'A guardar...';

  fetch('/submit', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{bullets_para_fallback: sel}})
  }})
  .then(r => r.json())
  .then(() => {{
    const nItems = Object.keys(sel).length;
    document.getElementById('submitBtn').textContent = 'Enviar para fallback';
    document.getElementById('submitBtn').disabled = false;
    document.getElementById('selectedCount').textContent =
      '✅ revisao.json guardado (' + totalBullets + ' bullet(s) em ' + nItems + ' item(ns)) — pode continuar a editar';
  }})
  .catch(err => {{
    document.getElementById('submitBtn').disabled = false;
    document.getElementById('submitBtn').textContent = 'Enviar para fallback';
    alert('Erro ao guardar: ' + err);
  }});
}}
</script>
</body>
</html>"""


# ── Servidor HTTP local ────────────────────────────────────────────────────────

def _build_html(criterios_path: Path) -> str:
    """Lê os ficheiros de critérios e renderiza o HTML de raiz (chamado a cada GET)."""
    criterios: list[CriterioRaw] = load_criterios(criterios_path)
    rejected_path = criterios_path.parent / "criterios_com_erro.json"
    if rejected_path.exists():
        criterios += load_criterios(rejected_path)

    known_ids = {c.id_item for c in criterios}
    missing_cards: list[tuple[str, int]] = []
    cotacoes_path = criterios_path.parent / "cotacoes_estrutura.json"
    if cotacoes_path.exists():
        cotacoes_data = json.loads(cotacoes_path.read_text(encoding="utf-8"))
        for item_id, pts in cotacoes_data.get("cotacoes", {}).items():
            if item_id not in known_ids:
                missing_cards.append((item_id, pts))

    def _sort_key(s: str) -> tuple:
        import re as _re
        m = _re.match(r"^([IVX]+)-(.+)$", s)
        grupo_part = m.group(1) if m else ""
        rest       = m.group(2) if m else s
        parts      = rest.replace(".", " ").split()
        return (grupo_part,) + tuple(p.zfill(3) if p.isdigit() else p for p in parts)

    criterios.sort(key=lambda c: _sort_key(c.id_item))
    missing_cards.sort(key=lambda t: _sort_key(t[0]))

    title  = criterios[0].fonte if criterios else criterios_path.parent.name
    n_mc   = sum(1 for c in criterios if c.tipo == "multiple_choice")
    n_or   = sum(1 for c in criterios if c.tipo == "open_response")
    n_warn = sum(1 for c in criterios if "warning" in c.status)
    n_err  = sum(1 for c in criterios if c.status == "error")

    all_items: list[str] = []
    idx = 1
    ci, mi = 0, 0
    while ci < len(criterios) or mi < len(missing_cards):
        take_crit = (mi >= len(missing_cards) or
                     (ci < len(criterios) and
                      _sort_key(criterios[ci].id_item) <= _sort_key(missing_cards[mi][0])))
        if take_crit:
            c = criterios[ci]
            extra_class = " error-item" if c.status == "error" else ""
            card = _render_criterio(c, idx)
            if extra_class:
                card = card.replace('class="criterio"', f'class="criterio{extra_class}"', 1)
            all_items.append(card)
            ci += 1
        else:
            all_items.append(_render_missing(missing_cards[mi][0], missing_cards[mi][1], idx))
            mi += 1
        idx += 1

    return _HTML_TEMPLATE.format(
        title=html.escape(title),
        total=len(criterios),
        n_mc=n_mc,
        n_or=n_or,
        n_warn=n_warn,
        n_err=n_err,
        criterios_html="\n".join(all_items),
    )


def _make_handler(output_path: Path, criterios_path: Path, done: threading.Event):
    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in ("/", "/index.html"):
                try:
                    body = _build_html(criterios_path).encode("utf-8")
                    status = 200
                    ct = "text/html; charset=utf-8"
                except Exception as exc:
                    body = (f"<html><body><pre>Erro ao renderizar página: "
                            f"{html.escape(str(exc))}</pre></body></html>").encode("utf-8")
                    status = 500
                    ct = "text/html; charset=utf-8"
                self.send_response(status)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()
            elif self.path.startswith("/imagens_extraidas/"):
                # Serve imagens extraídas pelo MinerU (relativas ao dir do markdown)
                img_rel = self.path.lstrip("/")
                img_path = criterios_path.parent / img_rel
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
            """Envia resposta JSON com headers correctos e flush — compatível com Safari."""
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))

            if self.path == "/submit":
                # Guarda revisao.json — servidor continua vivo até Ctrl+C
                output_path.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                self._send_json({"status": "ok"})

            elif self.path == "/edit":
                # Edição manual de bullet OU campo solucao (bullet_idx==-1)
                try:
                    item_id    = payload["item_id"]
                    bullet_idx = int(payload["bullet_idx"])
                    new_desc   = payload["descricao"].strip()
                    rejected_path = criterios_path.parent / "criterios_com_erro.json"
                    updated = False
                    for target_path in [criterios_path, rejected_path]:
                        if not target_path.exists():
                            continue
                        lst = json.loads(target_path.read_text(encoding="utf-8"))
                        for c in lst:
                            if c["id_item"] == item_id:
                                if bullet_idx == -1:
                                    # Editar campo solucao directamente
                                    c["solucao"] = new_desc
                                    updated = True
                                elif bullet_idx < len(c.get("criterios_parciais", [])):
                                    c["criterios_parciais"][bullet_idx]["descricao"] = new_desc
                                    updated = True
                                break
                        if updated:
                            target_path.write_text(
                                json.dumps(lst, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                            break
                    self._send_json({"status": "ok"} if updated
                                    else {"status": "error", "error": "item/bullet não encontrado"})
                except Exception as exc:
                    self._send_json({"status": "error", "error": str(exc)})

            elif self.path == "/edit-header":
                # Edição de id_item, tipo, resposta_correta — procura em aprovados e em erros
                try:
                    orig_id  = payload["orig_id"]
                    new_id   = payload.get("id_item", orig_id).strip()
                    new_tipo = payload.get("tipo", "open_response")
                    new_resp = (payload.get("resposta_correta") or "").strip().upper() or None
                    rejected_path = criterios_path.parent / "criterios_com_erro.json"
                    updated = False
                    tipo_changed = False
                    for target_path in [criterios_path, rejected_path]:
                        if not target_path.exists():
                            continue
                        lst = json.loads(target_path.read_text(encoding="utf-8"))
                        for c in lst:
                            if c["id_item"] == orig_id:
                                tipo_changed = c["tipo"] != new_tipo
                                c["id_item"] = new_id
                                c["tipo"]    = new_tipo
                                if new_tipo == "multiple_choice":
                                    c["resposta_correta"] = new_resp
                                updated = True
                                break
                        if updated:
                            target_path.write_text(
                                json.dumps(lst, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                            break
                    if updated:
                        self._send_json({"status": "ok", "reload": tipo_changed})
                    else:
                        self._send_json({"status": "error", "error": "item não encontrado"})
                except Exception as exc:
                    self._send_json({"status": "error", "error": str(exc)})

            elif self.path == "/approve":
                # Move item de criterios_com_erro.json para criterios_aprovados.json
                try:
                    item_id = payload["item_id"]
                    rejected_path = criterios_path.parent / "criterios_com_erro.json"
                    approved = json.loads(criterios_path.read_text(encoding="utf-8"))
                    rejected = json.loads(rejected_path.read_text(encoding="utf-8")) if rejected_path.exists() else []
                    item = None
                    new_rejected = []
                    for c in rejected:
                        if c["id_item"] == item_id:
                            item = c
                        else:
                            new_rejected.append(c)
                    if item is None:
                        self._send_json({"status": "error", "error": "item não encontrado nos rejeitados"})
                        return
                    item["status"] = "approved"
                    approved.append(item)
                    criterios_path.write_text(
                        json.dumps(approved, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    rejected_path.write_text(
                        json.dumps(new_rejected, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    self._send_json({"status": "ok"})
                except Exception as exc:
                    self._send_json({"status": "error", "error": str(exc)})

            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):  # silencia logs de acesso
            pass

    return _Handler


# ── Ponto de entrada ───────────────────────────────────────────────────────────

def run_cc_preview(
    criterios_path: Path,
    output_path: Path | None = None,
    port: int = _DEFAULT_PORT,
) -> Path:
    """
    Abre o preview interativo dos critérios no browser.

    Bloqueia até o utilizador clicar "Enviar para fallback" ou Ctrl+C.
    Escreve revisao.json e retorna o seu caminho.
    """
    criterios_path = criterios_path.resolve()
    if output_path is None:
        output_path = criterios_path.parent / "revisao.json"

    done = threading.Event()
    handler_class = _make_handler(output_path, criterios_path, done)

    import socketserver

    class _ReuseServer(socketserver.TCPServer):
        allow_reuse_address = True  # deve ser classe, não instância — fix: era definido após o bind

    with _ReuseServer(("localhost", port), handler_class) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()

        url = f"http://localhost:{port}"
        print(f"[cc_preview] A abrir {url}")
        print("[cc_preview] Seleccione bullets para revisão e clique 'Enviar para fallback'.")
        print("[cc_preview] Pode continuar a editar depois de submeter.")
        print("[cc_preview] Prima Ctrl+C para fechar o servidor quando terminar.")
        webbrowser.open(url)

        try:
            done.wait()
        except KeyboardInterrupt:
            print("\n[cc_preview] Cancelado pelo utilizador.")
            return output_path
        finally:
            httpd.shutdown()

    print(f"[cc_preview] ✅ {output_path}")
    return output_path
