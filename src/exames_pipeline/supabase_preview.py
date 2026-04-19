"""Módulo 7b — Preview editável puxando questões diretamente do Supabase.

Inicia um servidor HTTP local que:
- Busca questões via Supabase REST API (com filtros opcionais)
- Renderiza o mesmo HTML do module_preview.py
- Permite editar campos e salvar de volta ao Supabase via PATCH
- Suporta filtro por fonte (ano) e grupo
"""
from __future__ import annotations

import html
import json
import re
import socketserver
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from .config import Settings
from .module_preview import _md_to_html, _IMAGE_MD_RE, _render_question
from .schemas import Question, Alternative

# ── Supabase REST helpers ─────────────────────────────────────────────────────

def _sb_headers(settings: Settings) -> dict[str, str]:
    return {
        "apikey": settings.supabase_key,
        "Authorization": f"Bearer {settings.supabase_key}",
        "Content-Type": "application/json",
    }


def _fetch_questions(
    settings: Settings,
    fonte: str | None = None,
    grupo: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Busca questões do Supabase com filtros opcionais (schema v2).

    Faz embedded select de contextos para obter texto e imagens do contexto pai.
    Filtra por ``fonte`` (campo desnormalizado) para compatibilidade com o filtro UI.
    """
    select = "*,contextos!contexto_id(texto,imagens,grupo)"
    params: dict[str, str] = {
        "select": select,
        "order":  "numero_questao.asc,id_item.asc",
        "limit":  str(limit),
    }
    if fonte:
        params["fonte"] = f"eq.{fonte}"
    if grupo:
        params["grupo"] = f"eq.{grupo}"

    url = (f"{settings.supabase_url}/rest/v1/{settings.supabase_table}"
           f"?{urllib.parse.urlencode(params)}")
    req = urllib.request.Request(url, headers=_sb_headers(settings))
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _fetch_fontes(settings: Settings) -> list[str]:
    """Busca lista de fontes distintas (campo desnormalizado)."""
    url = (f"{settings.supabase_url}/rest/v1/{settings.supabase_table}"
           f"?select=fonte&order=fonte.asc")
    req = urllib.request.Request(url, headers={**_sb_headers(settings), "Prefer": "count=exact"})
    with urllib.request.urlopen(req, timeout=10) as r:
        rows = json.loads(r.read())
    return sorted({r["fonte"] for r in rows if r.get("fonte")})


_AI_REVIEW_PROMPT = """\
És um revisor especializado em provas de Matemática A (Portugal).
A questão abaixo foi extraída via OCR de um PDF oficial e pode ter erros.

Fonte de verdade:
O PDF oficial da prova é a referência máxima.
O JSON abaixo é apenas uma extração derivada desse PDF.
Sempre que houver divergência entre a extração e o PDF oficial, deve prevalecer o PDF oficial.

Importante:
Se o PDF original, imagens ou excertos visuais da fonte não estiverem realmente disponíveis no contexto desta revisão,
não inventes correções baseadas em suposição.
Nesses casos, limita-te a detetar apenas problemas claramente visíveis no JSON e a sinalizar incerteza quando a confirmação depender do PDF.

QUESTÃO (JSON):
{question_json}

Objetivo:
Analisar a questão com atenção e sugerir correções APENAS para problemas reais, claramente justificáveis e compatíveis com o PDF oficial.

Prioridades:
1. Erros de OCR: texto fundido, caracteres trocados, espaçamentos errados
2. LaTeX malformado: $ não fechados, comandos incorretos, espaços em branco desnecessários
3. Alternativas de escolha múltipla: contaminação com outro item, truncamento, ordem ou letra errada
4. Critérios de avaliação: descrição contaminada, texto incompleto, campo evidentemente deslocado
5. Tags / categorização: temas ou subtemas claramente incorretos

Regras de fidelidade:
- Não inventes conteúdo novo.
- Não reformules por estilo.
- Não “melhores” a redação só porque te parece estranha.
- Se o PDF original não estiver disponível para confirmar uma alteração factual, sê conservador.
- Em LaTeX e matemática, só sugiras correções quando houver forte evidência de erro.
- Se houver dúvida real, não corrijas; relata a dúvida no resumo ou em `evidencia`.

Regras especiais para LaTeX:
- O LaTeX final deve representar exatamente o que está no PDF oficial, não apenas uma forma matemática equivalente.
- Se o problema for apenas plausível mas não confirmável sem o PDF, não sugiras substituição agressiva.
- Dá prioridade a erros objetivos: delimitadores desequilibrados, comandos quebrados, símbolos partidos, expoentes/índices incorretos.

Responde APENAS com JSON válido, sem texto adicional:
{{
  "sugestoes": [
    {{
      "campo": "enunciado | alternativa_A | alternativa_B | ... | criterio_0 | criterio_1 | ... | solucao | tags | tema | subtema",
      "descricao": "descrição breve do problema encontrado",
      "evidencia": "porque esta alteração é justificada",
      "atual": "valor/texto atual",
      "sugerido": "valor/texto corrigido",
      "confianca": "alta | media | baixa"
    }}
  ],
  "resumo": "avaliação geral da qualidade da questão em 1-2 frases"
}}

Se não encontrares problemas, retorna {{"sugestoes": [], "resumo": "Questão sem problemas aparentes."}}
"""



def _patch_question(settings: Settings, sb_id: str, fields: dict[str, Any]) -> None:
    """Atualiza campos de uma questão no Supabase via PATCH."""
    url = f"{settings.supabase_url}/rest/v1/{settings.supabase_table}?id=eq.{urllib.parse.quote(sb_id)}"
    body = json.dumps(fields, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url, data=body, method="PATCH",
        headers={**_sb_headers(settings), "Prefer": "return=minimal"},
    )
    with urllib.request.urlopen(req, timeout=15):
        pass


# ── Dict → Question ──────────────────────────────────────────────────────────

def _substitute_image_urls(text: str, url_map: dict[str, str]) -> str:
    """Substitui caminhos locais de imagens no markdown por URLs do Supabase."""
    def _replace(m: re.Match) -> str:
        path = m.group(1)
        filename = path.split("/")[-1]
        full_url = url_map.get(filename, url_map.get(path, path))
        return f"![]({full_url})"
    return re.sub(r"!\[[^\]]*\]\(([^)]+)\)", _replace, text)


def _row_to_question(row: dict[str, Any]) -> Question:
    """Converte uma row do Supabase (schema v2) num objecto Question.

    Suporta:
    - imagens como jsonb [{url, descricao, alt}] ou text[] (compat retroativa)
    - contexto embebido via JOIN (contextos!contexto_id)
    - enunciado_contexto_pai reconstituído a partir de contextos.texto
    """
    # ── Alternativas ──────────────────────────────────────────────────────────
    alts = row.get("alternativas") or []
    if isinstance(alts, str):
        alts = json.loads(alts)
    alternativas = [Alternative(**a) if isinstance(a, dict) else a for a in alts]

    # ── Critérios e resoluções ────────────────────────────────────────────────
    cp = row.get("criterios_parciais") or []
    if isinstance(cp, str): cp = json.loads(cp)
    ra = row.get("resolucoes_alternativas") or []
    if isinstance(ra, str): ra = json.loads(ra)

    # ── Imagens (schema v2: jsonb [{url,descricao,alt}]; compat: text[]) ──────
    imagens_raw = row.get("imagens") or []
    if isinstance(imagens_raw, str): imagens_raw = json.loads(imagens_raw)
    if imagens_raw and isinstance(imagens_raw[0], dict):
        # Schema v2 — extrair URLs e construir descricoes_imagens
        imagens_urls     = [img["url"] for img in imagens_raw]
        descricoes_imgs  = {img["url"]: img.get("descricao", "") for img in imagens_raw}
    else:
        # Compat retroativa — lista de strings
        imagens_urls    = list(imagens_raw)
        descricoes_imgs = {}

    # ── Contexto pai (schema v2: embedded join; compat: campo texto) ──────────
    ctx = row.get("contextos") or {}
    if isinstance(ctx, str): ctx = json.loads(ctx)
    enunciado_ctx_pai = ctx.get("texto", "") if isinstance(ctx, dict) else ""

    ctx_imagens_raw = ctx.get("imagens", []) if isinstance(ctx, dict) else []
    if isinstance(ctx_imagens_raw, str): ctx_imagens_raw = json.loads(ctx_imagens_raw)
    if ctx_imagens_raw and isinstance(ctx_imagens_raw[0], dict):
        imagens_contexto = [img["url"] for img in ctx_imagens_raw]
        for img in ctx_imagens_raw:
            descricoes_imgs[img["url"]] = img.get("descricao", "")
    else:
        imagens_contexto = list(ctx_imagens_raw)

    # ── Substituir paths locais no enunciado por URLs ─────────────────────────
    all_urls = imagens_urls + imagens_contexto
    url_map  = {u.split("/")[-1]: u for u in all_urls if u.startswith("http")}
    enunciado_raw = row.get("enunciado", "")
    if url_map:
        enunciado_raw = _substitute_image_urls(enunciado_raw, url_map)

    return Question(
        numero_questao=int(row.get("numero_questao", 0)),
        enunciado=enunciado_raw,
        alternativas=alternativas,
        id_item=row.get("id_item", ""),
        ordem_item=row.get("ordem_item"),
        numero_principal=row.get("numero_principal"),
        subitem=row.get("subitem"),
        tipo_item=row.get("tipo_item", "unknown"),
        materia=row.get("materia", ""),
        tema=row.get("tema", ""),
        subtema=row.get("subtema", ""),
        tags=list(row.get("tags") or []),
        imagens=imagens_urls,
        imagens_contexto=imagens_contexto,
        pagina_origem=row.get("pagina_origem"),
        resposta_correta=row.get("resposta_correta"),
        fonte=row.get("fonte", ""),
        status=row.get("status", "approved"),
        observacoes=list(row.get("observacoes") or []),
        enunciado_contexto_pai=enunciado_ctx_pai,
        descricoes_imagens=descricoes_imgs,
        descricao_breve=row.get("descricao_breve", ""),
        solucao=row.get("solucao", ""),
        criterios_parciais=cp,
        resolucoes_alternativas=ra,
        grupo=row.get("grupo", ""),
    )


def _inject_sb_buttons(card: str, sb_id: str) -> str:
    """Injeta data-sb-id e botão 🤖 Rever no article."""
    ai_btn = (f'<button class="ai-review-btn" onclick="aiReview(this)"'
              f' data-sb-id="{html.escape(sb_id)}" title="Revisão por IA">🤖 Rever</button>')
    card = card.replace('<article class="question',
                        f'<article data-sb-id="{html.escape(sb_id)}" class="question', 1)
    card = card.replace('<span class="q-fonte">', ai_btn + '<span class="q-fonte">', 1)
    return card


# ── HTML ──────────────────────────────────────────────────────────────────────

_CSS_EXTRA = """
/* Botão de revisão IA */
.ai-review-btn {
  font-size: .75rem; padding: .2rem .55rem;
  background: #7c3aed; color: #fff; border: none;
  border-radius: 999px; cursor: pointer; white-space: nowrap;
  transition: background .15s;
}
.ai-review-btn:hover { background: #6d28d9; }
.ai-review-btn.loading { background: #a78bfa; cursor: wait; }

/* Painel lateral de revisão IA */
#ai-panel {
  position: fixed; top: 0; right: -440px; width: 420px; height: 100vh;
  background: #fff; border-left: 2px solid #ede9fe;
  box-shadow: -4px 0 24px rgba(0,0,0,.12);
  display: flex; flex-direction: column;
  transition: right .3s ease; z-index: 1000;
  font-size: .85rem;
}
#ai-panel.open { right: 0; }
#ai-panel-header {
  display: flex; align-items: center; gap: .5rem;
  padding: .85rem 1rem; border-bottom: 1px solid #ede9fe;
  background: #f5f3ff;
}
#ai-panel-header h3 { margin: 0; font-size: .95rem; color: #4c1d95; flex: 1; }
#ai-panel-close {
  background: none; border: none; font-size: 1.1rem;
  cursor: pointer; color: #7c3aed; padding: .1rem .3rem;
}
#ai-panel-body { flex: 1; overflow-y: auto; padding: 1rem; }
#ai-panel-footer { padding: .75rem 1rem; border-top: 1px solid #ede9fe; }

/* Sugestão individual */
.ai-suggestion {
  border: 1px solid #ede9fe; border-radius: 8px;
  margin-bottom: .75rem; overflow: hidden;
}
.ai-suggestion-header {
  display: flex; align-items: center; gap: .4rem;
  padding: .45rem .75rem; background: #f5f3ff;
}
.ai-campo-badge {
  font-size: .7rem; font-weight: 700; background: #7c3aed; color: #fff;
  border-radius: 4px; padding: .1rem .4rem; white-space: nowrap;
}
.ai-conf-badge {
  font-size: .68rem; border-radius: 4px; padding: .1rem .35rem; font-weight: 600;
}
.ai-conf-alta   { background: #dcfce7; color: #15803d; }
.ai-conf-media  { background: #fef9c3; color: #854d0e; }
.ai-conf-baixa  { background: #fee2e2; color: #b91c1c; }
.ai-descricao { padding: .4rem .75rem; color: #4b5563; font-style: italic; }
.ai-diff {
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 0; border-top: 1px solid #ede9fe;
}
.ai-diff-atual, .ai-diff-sug {
  padding: .45rem .65rem; font-size: .78rem;
  white-space: pre-wrap; word-break: break-word;
}
.ai-diff-atual { background: #fff1f2; color: #9f1239; border-right: 1px solid #ede9fe; }
.ai-diff-sug   { background: #f0fdf4; color: #15803d; }
.ai-diff-label { font-size: .65rem; font-weight: 700; opacity: .7; display: block; margin-bottom: .2rem; }
.ai-suggestion-actions {
  display: flex; gap: .4rem; padding: .45rem .75rem;
  border-top: 1px solid #ede9fe;
}
.ai-accept-btn {
  flex: 1; background: #16a34a; color: #fff; border: none;
  border-radius: 6px; padding: .3rem; cursor: pointer; font-size: .78rem;
}
.ai-accept-btn:hover { background: #15803d; }
.ai-reject-btn {
  background: #f1f5f9; color: #64748b; border: none;
  border-radius: 6px; padding: .3rem .7rem; cursor: pointer; font-size: .78rem;
}
.ai-reject-btn:hover { background: #e2e8f0; }
.ai-accepted { opacity: .45; pointer-events: none; }
.ai-resumo {
  background: #f5f3ff; border: 1px solid #ede9fe; border-radius: 8px;
  padding: .65rem .9rem; margin-bottom: .9rem; color: #4c1d95; font-style: italic;
}
.ai-spinner {
  display: flex; align-items: center; justify-content: center;
  gap: .6rem; padding: 2rem; color: #7c3aed;
}
.ai-spinner::before {
  content: ''; width: 22px; height: 22px;
  border: 3px solid #ede9fe; border-top-color: #7c3aed;
  border-radius: 50%; animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Supabase preview extras */
.filter-bar {
  position: sticky; top: 0; z-index: 100;
  background: #fff; border-bottom: 1px solid #e2e8f0;
  padding: .6rem 1.5rem; display: flex; gap: .75rem; align-items: center;
  flex-wrap: wrap;
}
.filter-bar label { font-size: .82rem; font-weight: 600; color: #374151; }
.filter-bar select, .filter-bar input {
  font-size: .82rem; border: 1px solid #d1d5db; border-radius: 6px;
  padding: .3rem .5rem; background: #f9fafb;
}
.filter-bar button {
  font-size: .82rem; background: #3b82f6; color: #fff;
  border: none; border-radius: 6px; padding: .35rem .8rem; cursor: pointer;
}
.filter-bar button:hover { background: #2563eb; }
.sb-badge {
  font-size: .7rem; background: #10b981; color: #fff;
  border-radius: 999px; padding: .1rem .5rem; margin-left: .4rem;
}
"""


def _build_html(
    rows: list[dict[str, Any]],
    fontes: list[str],
    selected_fonte: str,
    selected_grupo: str,
) -> str:
    questions = [_row_to_question(r) for r in rows]
    sb_ids = {r["id_item"] + "|" + r.get("grupo", ""): r["id"] for r in rows}

    cards = ""
    seen_ctx: set[str] = set()
    for i, (row, q) in enumerate(zip(rows, questions)):
        sb_id = row["id"]

        # Renderizar bloco de contexto uma vez antes da primeira subquestão do grupo
        ctx_id = row.get("contexto_id")
        ctx_data = row.get("contextos") or {}
        if isinstance(ctx_data, str):
            import json as _json
            ctx_data = _json.loads(ctx_data)
        if ctx_id and ctx_id not in seen_ctx and isinstance(ctx_data, dict) and ctx_data.get("texto"):
            seen_ctx.add(ctx_id)
            ctx_label = html.escape(row.get("grupo") or "")
            ctx_item  = html.escape(row.get("id_item", "").split(".")[0])  # ex: "II-2"
            ctx_html  = _md_to_html(ctx_data["texto"])
            # Imagens do contexto
            ctx_imgs_html = ""
            for img in (ctx_data.get("imagens") or []):
                if isinstance(img, dict):
                    url = html.escape(img.get("url", ""))
                    ctx_imgs_html += f'<img class="q-img" src="{url}" alt="">'
            if ctx_imgs_html:
                ctx_imgs_html = f'<div class="q-images">{ctx_imgs_html}</div>'
            cards += f"""
<article class="question context-stem-card" id="ctx-{ctx_id}">
  <header class="q-header">
    <span class="id-input" style="font-weight:700;padding:2px 6px">{ctx_item}</span>
    <span class="status-badge" style="background:#dbeafe;color:#1d4ed8">CTX</span>
    <span class="q-fonte" style="color:#6b7280">Enunciado partilhado</span>
  </header>
  <div class="q-body">
    <div class="field-text enunciado-text" style="background:#f0f9ff;border-left:3px solid #3b82f6;padding-left:10px">{ctx_html}</div>
    {ctx_imgs_html}
  </div>
</article>"""

        card = _render_question(q, i + 1, show_context=False)
        card = _inject_sb_buttons(card, sb_id)
        cards += card

    fonte_opts = "".join(
        f'<option value="{html.escape(f)}" {"selected" if f == selected_fonte else ""}>{html.escape(f)}</option>'
        for f in ["", *fontes]
    )

    grupos_opts = "".join(
        f'<option value="{html.escape(g)}" {"selected" if g == selected_grupo else ""}>{html.escape(g)}</option>'
        for g in ["", "I", "II", "III", "IV"]
    )

    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="utf-8">
<title>Preview Supabase — Questões</title>
<script>
window.MathJax = {{
  tex: {{ inlineMath: [['$','$'],['\\\\(','\\\\)']], displayMath: [['$$','$$'],['\\\\[','\\\\]']] }},
  options: {{ skipHtmlTags: ['script','noscript','style','textarea','pre'] }}
}};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js" async></script>
<style>
{_get_preview_css()}
{_CSS_EXTRA}
</style>
</head>
<body>
<div class="filter-bar">
  <label>Fonte:</label>
  <select id="sel-fonte" onchange="applyFilter()">
    <option value="">Todas</option>
    {fonte_opts}
  </select>
  <label>Grupo:</label>
  <select id="sel-grupo" onchange="applyFilter()">
    <option value="">Todos</option>
    {grupos_opts}
  </select>
  <span class="sb-badge">Supabase</span>
  <span style="font-size:.8rem;color:#6b7280;">{len(rows)} questão(ões)</span>
</div>
<!-- Painel de revisão IA -->
<div id="ai-panel">
  <div id="ai-panel-header">
    <h3>🤖 Revisão IA</h3>
    <button id="ai-panel-close" onclick="closeAiPanel()" title="Fechar">✖</button>
  </div>
  <div id="ai-panel-body"><p style="color:#9ca3af;padding:1rem">Clique em 🤖 Rever numa questão.</p></div>
</div>

<div class="container" id="main-container">
{cards}
</div>

<script>
// ── Filtro ─────────────────────────────────────────────────────────────────
function applyFilter() {{
  const fonte = document.getElementById('sel-fonte').value;
  const grupo = document.getElementById('sel-grupo').value;
  const params = new URLSearchParams();
  if (fonte) params.set('fonte', fonte);
  if (grupo) params.set('grupo', grupo);
  window.location.href = '/?' + params.toString();
}}

// ── Re-renderizar card após qualquer save ─────────────────────────────────
function _rerenderCard(article, sbId) {{
  fetch('/rerender?sb_id=' + encodeURIComponent(sbId))
    .then(r => r.text())
    .then(newHtml => {{
      const tmp = document.createElement('div');
      tmp.innerHTML = newHtml;
      const newArticle = tmp.querySelector('article');
      if (newArticle) {{
        article.replaceWith(newArticle);
        if (window.MathJax) MathJax.typesetPromise([newArticle]);
      }}
    }})
    .catch(e => console.error('Rerender falhou:', e));
}}

// ── Editar campos genéricos (enunciado, solucao, etc.) ────────────────────
function toggleEdit(btn) {{
  const fieldBlock = btn.closest('.field-block');
  if (!fieldBlock) return;
  const fieldText = fieldBlock.querySelector('.field-text');
  const editArea  = fieldBlock.querySelector('.edit-area');
  if (!editArea) return;
  const isEditing = editArea.style.display !== 'none';
  if (isEditing) {{
    fieldText.style.display = '';
    editArea.style.display  = 'none';
    btn.textContent = '✏️';
  }} else {{
    fieldText.style.display = 'none';
    editArea.style.display  = '';
    btn.textContent = '✖';
  }}
}}

function saveEdit(btn) {{
  const fieldBlock = btn.closest('.field-block');
  const article    = btn.closest('article');
  const sbId  = article.dataset.sbId;
  const field = btn.dataset.field;
  const value = fieldBlock.querySelector('.edit-ta').value;
  fetch('/patch', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ sb_id: sbId, field: field, value: value }})
  }}).then(r => r.json()).then(d => {{
    if (d.status === 'ok') {{
      location.reload();
    }} else {{
      alert('Erro: ' + (d.error || 'desconhecido'));
    }}
  }}).catch(e => alert('Erro: ' + e));
}}

function cancelEdit(btn) {{
  // Tenta alternativa (li) primeiro
  const li = btn.closest('li');
  if (li && li.querySelector('.edit-area')) {{
    li.querySelector('.edit-area').style.display = 'none';
    const altText = li.querySelector('.alt-text');
    if (altText) altText.style.display = '';
    const editBtn = li.querySelector('.edit-btn');
    if (editBtn) editBtn.textContent = '✏️';
    return;
  }}
  // Campo genérico (field-block)
  const fieldBlock = btn.closest('.field-block');
  if (fieldBlock) {{
    const editArea = fieldBlock.querySelector('.edit-area');
    if (editArea) editArea.style.display = 'none';
    const fieldText = fieldBlock.querySelector('.field-text');
    if (fieldText) fieldText.style.display = '';
    const editBtn = fieldBlock.querySelector('.edit-btn');
    if (editBtn) editBtn.textContent = '✏️';
  }}
}}

// ── Alternativas ──────────────────────────────────────────────────────────
function toggleAltEdit(btn) {{
  const li = btn.closest('li');
  const fieldText = li.querySelector('.alt-text');
  const editArea  = li.querySelector('.edit-area');
  const isEditing = editArea.style.display !== 'none';
  if (isEditing) {{
    fieldText.style.display = '';
    editArea.style.display  = 'none';
    btn.textContent = '✏️';
  }} else {{
    fieldText.style.display = 'none';
    editArea.style.display  = '';
    btn.textContent = '✖';
  }}
}}

function saveAltEdit(btn) {{
  const li      = btn.closest('li');
  const article = btn.closest('article');
  const sbId  = article.dataset.sbId;
  const letra = btn.dataset.letra;
  const value = li.querySelector('.edit-ta').value;
  fetch('/patch-alt', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ sb_id: sbId, letra: letra, texto: value }})
  }}).then(r => r.json()).then(d => {{
    if (d.status === 'ok') {{
      location.reload();
    }} else {{
      alert('Erro: ' + (d.error || 'desconhecido'));
    }}
  }}).catch(e => alert('Erro: ' + e));
}}

// ── Header (id_item, tipo_item, resposta_correta) ─────────────────────────
function saveHeader(btn) {{
  const article = btn.closest('article');
  const sbId = article.dataset.sbId;
  const payload = {{ sb_id: sbId }};
  article.querySelectorAll('.header-input, .header-select').forEach(el => {{
    const field = el.dataset.field;
    if (field) payload[field] = el.value;
  }});
  fetch('/patch-header', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(payload)
  }}).then(r => r.json()).then(d => {{
    if (d.status === 'ok') {{
      location.reload();
    }} else {{
      alert('Erro: ' + (d.error || 'desconhecido'));
    }}
  }}).catch(e => alert('Erro: ' + e));
}}

// ── Critérios parciais ────────────────────────────────────────────────────
function toggleCcEdit(btn) {{
  const tr = btn.closest('tr');
  tr.querySelectorAll('.cc-row-content').forEach(el => {{
    el.style.display = el.style.display === 'none' ? '' : 'none';
  }});
  tr.querySelectorAll('.cc-edit-area').forEach(el => {{
    el.style.display = el.style.display === 'none' ? '' : 'none';
  }});
  btn.textContent = btn.textContent === '✏️' ? '✖' : '✏️';
}}

function saveCcEdit(btn) {{
  const tr = btn.closest('tr');
  const article = btn.closest('article');
  const sbId = article.dataset.sbId;
  const ccIdx = parseInt(btn.dataset.ccIdx);
  const pontos = tr.querySelector('.cc-pts-input').value;
  const descricao = tr.querySelector('.cc-desc-ta').value;
  fetch('/patch-cc', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ sb_id: sbId, cc_idx: ccIdx, pontos: pontos, descricao: descricao }})
  }}).then(r => r.json()).then(d => {{
    if (d.status === 'ok') location.reload();
    else alert('Erro: ' + (d.error || 'desconhecido'));
  }}).catch(e => alert('Erro: ' + e));
}}

function cancelCcEdit(btn) {{
  const tr = btn.closest('tr');
  tr.querySelectorAll('.cc-row-content').forEach(el => el.style.display = '');
  tr.querySelectorAll('.cc-edit-area').forEach(el => el.style.display = 'none');
  const editBtn = tr.querySelector('.cc-edit-btn');
  if (editBtn) editBtn.textContent = '✏️';
}}

function deleteCcRow(btn) {{
  if (!confirm('Remover este critério?')) return;
  const article = btn.closest('article');
  const sbId = article.dataset.sbId;
  const ccIdx = parseInt(btn.dataset.ccIdx);
  fetch('/patch-cc', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ sb_id: sbId, cc_idx: ccIdx, delete: true }})
  }}).then(r => r.json()).then(d => {{
    if (d.status === 'ok') location.reload();
    else alert('Erro: ' + (d.error || 'desconhecido'));
  }}).catch(e => alert('Erro: ' + e));
}}

function addCcRow(btn) {{
  const article = btn.closest('article');
  const sbId = article.dataset.sbId;
  fetch('/patch-cc', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ sb_id: sbId, cc_idx: -1, pontos: '0', descricao: '' }})
  }}).then(r => r.json()).then(d => {{
    if (d.status === 'ok') location.reload();
    else alert('Erro: ' + (d.error || 'desconhecido'));
  }}).catch(e => alert('Erro: ' + e));
}}

// ── Resoluções alternativas ───────────────────────────────────────────────
function toggleAltResEdit(btn) {{
  const li = btn.closest('li');
  li.querySelectorAll('.cc-row-content').forEach(el => {{
    el.style.display = el.style.display === 'none' ? '' : 'none';
  }});
  li.querySelectorAll('.cc-edit-area').forEach(el => {{
    el.style.display = el.style.display === 'none' ? '' : 'none';
  }});
  btn.textContent = btn.textContent === '✏️' ? '✖' : '✏️';
}}

function saveAltResEdit(btn) {{
  const li = btn.closest('li');
  const article = btn.closest('article');
  const sbId = article.dataset.sbId;
  const altIdx = parseInt(btn.dataset.altIdx);
  const value = li.querySelector('.cc-altres-ta').value;
  fetch('/patch-altres', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ sb_id: sbId, alt_idx: altIdx, value: value }})
  }}).then(r => r.json()).then(d => {{
    if (d.status === 'ok') location.reload();
    else alert('Erro: ' + (d.error || 'desconhecido'));
  }}).catch(e => alert('Erro: ' + e));
}}

function cancelAltResEdit(btn) {{
  const li = btn.closest('li');
  li.querySelectorAll('.cc-row-content').forEach(el => el.style.display = '');
  li.querySelectorAll('.cc-edit-area').forEach(el => el.style.display = 'none');
  const editBtn = li.querySelector('.cc-edit-btn');
  if (editBtn) editBtn.textContent = '✏️';
}}

// ── Painel de revisão IA ──────────────────────────────────────────────────
let _currentAiArticle = null;
let _currentAiSbId    = null;

function closeAiPanel() {{
  document.getElementById('ai-panel').classList.remove('open');
  _currentAiArticle = null;
  _currentAiSbId    = null;
}}

function aiReview(btn) {{
  const sbId = btn.dataset.sbId;
  const article = btn.closest('article');
  _currentAiArticle = article;
  _currentAiSbId    = sbId;

  const panel = document.getElementById('ai-panel');
  const body  = document.getElementById('ai-panel-body');
  panel.classList.add('open');
  body.innerHTML = '<div class="ai-spinner">A consultar IA…</div>';
  btn.classList.add('loading');
  btn.textContent = '⏳';

  fetch('/ai-review', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ sb_id: sbId }})
  }}).then(r => r.json()).then(d => {{
    btn.classList.remove('loading');
    btn.textContent = '🤖 Rever';
    if (d.status === 'ok') {{
      _renderAiSuggestions(d.resumo, d.sugestoes, sbId);
    }} else {{
      body.innerHTML = `<p style="color:#ef4444">Erro: ${{d.error || 'desconhecido'}}</p>`;
    }}
  }}).catch(e => {{
    btn.classList.remove('loading');
    btn.textContent = '🤖 Rever';
    body.innerHTML = `<p style="color:#ef4444">Erro: ${{e}}</p>`;
  }});
}}

function _confClass(c) {{
  if (c === 'alta')  return 'ai-conf-alta';
  if (c === 'media') return 'ai-conf-media';
  return 'ai-conf-baixa';
}}

function _renderAiSuggestions(resumo, sugestoes, sbId) {{
  const body = document.getElementById('ai-panel-body');
  if (!sugestoes || sugestoes.length === 0) {{
    body.innerHTML = `<div class="ai-resumo">${{resumo || 'Sem sugestões.'}}</div>
      <p style="color:#16a34a;text-align:center">✅ Questão sem problemas aparentes!</p>`;
    return;
  }}
  let html = `<div class="ai-resumo">${{resumo || ''}}</div>`;
  sugestoes.forEach((s, idx) => {{
    const confClass = _confClass(s.confianca);
    html += `<div class="ai-suggestion" id="ai-sug-${{idx}}">
  <div class="ai-suggestion-header">
    <span class="ai-campo-badge">${{s.campo || '?'}}</span>
    <span class="ai-conf-badge ${{confClass}}">${{s.confianca || '?'}}</span>
    <span style="flex:1;font-size:.78rem;color:#374151">${{s.descricao || ''}}</span>
  </div>
  <div class="ai-diff">
    <div class="ai-diff-atual"><span class="ai-diff-label">ATUAL</span>${{_escHtml(s.atual || '')}}</div>
    <div class="ai-diff-sug"><span class="ai-diff-label">SUGERIDO</span>${{_escHtml(s.sugerido || '')}}</div>
  </div>
  <div class="ai-suggestion-actions">
    <button class="ai-accept-btn" onclick="acceptSuggestion(${{idx}}, '${{sbId}}')" data-idx="${{idx}}">✅ Aceitar</button>
    <button class="ai-reject-btn" onclick="rejectSuggestion(${{idx}})">✗ Rejeitar</button>
  </div>
</div>`;
  }});
  body.innerHTML = html;
  // Guardar sugestões no painel para aceitar depois
  document.getElementById('ai-panel').dataset.sugestoes = JSON.stringify(sugestoes);
}}

function _escHtml(s) {{
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

function rejectSuggestion(idx) {{
  const el = document.getElementById('ai-sug-' + idx);
  if (el) el.classList.add('ai-accepted');
}}

function acceptSuggestion(idx, sbId) {{
  const panel     = document.getElementById('ai-panel');
  const sugestoes = JSON.parse(panel.dataset.sugestoes || '[]');
  const s = sugestoes[idx];
  if (!s) return;
  const campo = s.campo || '';
  const valor = s.sugerido || '';
  let endpoint = '/patch';
  let payload  = {{ sb_id: sbId }};

  if (campo === 'enunciado' || campo === 'solucao' || campo === 'tema' ||
      campo === 'subtema' || campo === 'materia' || campo === 'descricao_breve') {{
    payload.field = campo; payload.value = valor;

  }} else if (campo.startsWith('alternativa_')) {{
    const letra = campo.replace('alternativa_', '').toUpperCase();
    endpoint = '/patch-alt';
    payload  = {{ sb_id: sbId, letra: letra, texto: valor }};

  }} else if (campo.startsWith('criterio_')) {{
    const ccIdx = parseInt(campo.replace('criterio_', ''));
    endpoint = '/patch-cc';
    // O agente devolve o texto da descrição como sugerido; pontos ficam iguais
    payload = {{ sb_id: sbId, cc_idx: ccIdx, descricao: valor, pontos: '' }};

  }} else {{
    alert('Campo "' + campo + '" não suportado para aceitação automática. Edita manualmente.');
    return;
  }}

  fetch(endpoint, {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(payload)
  }}).then(r => r.json()).then(d => {{
    if (d.status === 'ok') {{
      document.getElementById('ai-sug-' + idx).classList.add('ai-accepted');
      if (_currentAiArticle) _rerenderCard(_currentAiArticle, sbId);
    }} else {{
      alert('Erro ao aceitar: ' + (d.error || '?'));
    }}
  }}).catch(e => alert('Erro: ' + e));
}}

// Mostrar botão salvar quando header muda
document.addEventListener('change', function(e) {{
  if (e.target.matches('.header-input, .header-select, .mc-resp-input')) {{
    const hdr = e.target.closest('header');
    if (hdr) {{ const btn = hdr.querySelector('.header-save-btn'); if (btn) btn.style.display = ''; }}
  }}
}});
document.addEventListener('input', function(e) {{
  if (e.target.matches('.header-input, .mc-resp-input')) {{
    const hdr = e.target.closest('header');
    if (hdr) {{ const btn = hdr.querySelector('.header-save-btn'); if (btn) btn.style.display = ''; }}
  }}
}});
</script>
</body>
</html>"""


def _get_preview_css() -> str:
    """Extrai o CSS embutido no _HTML_TEMPLATE do module_preview."""
    from . import module_preview as _mp
    m = re.search(r"<style>(.*?)</style>", _mp._HTML_TEMPLATE, re.DOTALL)
    if m:
        # O template usa {{ }} para escapar chaves do format() — desfazer escape
        return m.group(1).replace("{{", "{").replace("}}", "}")
    return "body { font-family: sans-serif; max-width: 900px; margin: 0 auto; padding: 1rem; }"


# ── Enunciado com botão de edição ────────────────────────────────────────────

def _render_enunciado_with_edit(q: Question) -> str:
    """Sobrescreve o enunciado block para incluir área de edição."""
    enunciado_html = _md_to_html(q.enunciado)
    enunciado_esc = html.escape(q.enunciado)
    return f"""<div class="enunciado-block">
  <div class="enunciado-field-text">{enunciado_html}</div>
  <button class="edit-enunciado-btn" onclick="toggleEdit(this)" title="Editar enunciado">✏️</button>
  <div class="enunciado-edit-area" style="display:none">
    <textarea class="enunciado-ta" rows="6" style="width:100%;font-family:monospace">{enunciado_esc}</textarea>
    <div class="edit-actions">
      <button class="save-btn" onclick="saveEnunciado(this)">Guardar</button>
      <button class="cancel-btn" onclick="cancelEdit(this)">Cancelar</button>
    </div>
  </div>
</div>"""


# ── Handler HTTP ──────────────────────────────────────────────────────────────

def _make_handler(settings: Settings):
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def _send(self, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()

        def _send_json(self, data: dict) -> None:
            body = json.dumps(data, ensure_ascii=False).encode()
            self._send(body, "application/json; charset=utf-8")

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/rerender":
                sb_id = params.get("sb_id", [""])[0]
                self._handle_rerender(sb_id)
                return

            fonte = params.get("fonte", [""])[0]
            grupo = params.get("grupo", [""])[0]

            try:
                rows = _fetch_questions(settings, fonte or None, grupo or None)
                fontes = _fetch_fontes(settings)
                page = _build_html(rows, fontes, fonte, grupo)
                self._send(page.encode("utf-8"))
            except Exception as exc:
                body = f"<pre>Erro: {html.escape(str(exc))}</pre>".encode()
                self.send_response(500)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def _handle_rerender(self, sb_id: str) -> None:
            try:
                url = (f"{settings.supabase_url}/rest/v1/{settings.supabase_table}"
                       f"?id=eq.{urllib.parse.quote(sb_id)}&select=*")
                req = urllib.request.Request(url, headers=_sb_headers(settings))
                with urllib.request.urlopen(req, timeout=10) as r:
                    rows = json.loads(r.read())
                if not rows:
                    self._send(b"<article><p>Questao nao encontrada</p></article>")
                    return
                row = rows[0]
                q = _row_to_question(row)
                card = _render_question(q, 0)
                card = _inject_sb_buttons(card, sb_id)
                self._send(card.encode("utf-8"))
            except Exception as exc:
                self._send(
                    f"<article><p>Erro: {html.escape(str(exc))}</p></article>".encode()
                )

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))

                if self.path == "/patch":
                    self._handle_patch(payload)
                elif self.path == "/patch-alt":
                    self._handle_patch_alt(payload)
                elif self.path == "/patch-header":
                    self._handle_patch_header(payload)
                elif self.path == "/patch-cc":
                    self._handle_patch_cc(payload)
                elif self.path == "/patch-altres":
                    self._handle_patch_altres(payload)
                elif self.path == "/ai-review":
                    self._handle_ai_review(payload)
                else:
                    self.send_response(404)
                    self.end_headers()
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

        def _handle_patch(self, payload: dict) -> None:
            sb_id = payload.get("sb_id", "")
            field = payload.get("field", "")
            value = payload.get("value", "")
            allowed = {"enunciado", "solucao", "resposta_correta", "descricao_breve",
                       "tema", "subtema", "materia", "tags"}
            if field not in allowed:
                self._send_json({"status": "error", "error": f"Campo '{field}' não editável"})
                return
            try:
                _patch_question(settings, sb_id, {field: value})
                rendered = _md_to_html(value) if field in {"enunciado", "solucao"} else html.escape(value)
                self._send_json({"status": "ok", "rendered": rendered})
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

        def _handle_patch_alt(self, payload: dict) -> None:
            sb_id = payload.get("sb_id", "")
            letra = payload.get("letra", "")
            novo_texto = payload.get("texto", "")
            # Buscar questão, atualizar alternativa e fazer PATCH
            try:
                url = (f"{settings.supabase_url}/rest/v1/{settings.supabase_table}"
                       f"?id=eq.{urllib.parse.quote(sb_id)}&select=alternativas")
                req = urllib.request.Request(url, headers=_sb_headers(settings))
                with urllib.request.urlopen(req, timeout=10) as r:
                    rows = json.loads(r.read())
                if not rows:
                    self._send_json({"status": "error", "error": "Questão não encontrada"})
                    return
                alts = rows[0].get("alternativas") or []
                if isinstance(alts, str):
                    alts = json.loads(alts)
                updated = False
                for alt in alts:
                    if isinstance(alt, dict) and alt.get("letra") == letra:
                        alt["texto"] = novo_texto
                        updated = True
                if not updated:
                    self._send_json({"status": "error", "error": f"Alternativa '{letra}' não encontrada"})
                    return
                _patch_question(settings, sb_id, {"alternativas": alts})
                self._send_json({"status": "ok", "rendered": _md_to_html(novo_texto)})
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

        def _fetch_field(self, sb_id: str, field: str):
            """Busca um campo JSONB de uma questão pelo id Supabase."""
            url = (f"{settings.supabase_url}/rest/v1/{settings.supabase_table}"
                   f"?id=eq.{urllib.parse.quote(sb_id)}&select={field}")
            req = urllib.request.Request(url, headers=_sb_headers(settings))
            with urllib.request.urlopen(req, timeout=10) as r:
                rows = json.loads(r.read())
            if not rows:
                raise ValueError("Questão não encontrada")
            val = rows[0].get(field) or []
            if isinstance(val, str):
                val = json.loads(val)
            return val

        def _handle_patch_cc(self, payload: dict) -> None:
            sb_id   = payload.get("sb_id", "")
            cc_idx  = int(payload.get("cc_idx", -1))
            delete  = payload.get("delete", False)
            try:
                criterios = self._fetch_field(sb_id, "criterios_parciais")
                if delete:
                    if 0 <= cc_idx < len(criterios):
                        criterios.pop(cc_idx)
                    else:
                        self._send_json({"status": "error", "error": "Índice inválido"}); return
                elif cc_idx == -1:
                    # Adicionar novo
                    criterios.append({"pontos": payload.get("pontos", "0"),
                                      "descricao": payload.get("descricao", "")})
                else:
                    if 0 <= cc_idx < len(criterios):
                        criterios[cc_idx]["pontos"]    = payload.get("pontos", criterios[cc_idx].get("pontos"))
                        criterios[cc_idx]["descricao"] = payload.get("descricao", criterios[cc_idx].get("descricao", ""))
                    else:
                        self._send_json({"status": "error", "error": "Índice inválido"}); return
                _patch_question(settings, sb_id, {"criterios_parciais": criterios})
                self._send_json({"status": "ok"})
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

        def _handle_patch_altres(self, payload: dict) -> None:
            sb_id   = payload.get("sb_id", "")
            alt_idx = int(payload.get("alt_idx", -1))
            value   = payload.get("value", "")
            try:
                altres = self._fetch_field(sb_id, "resolucoes_alternativas")
                if 0 <= alt_idx < len(altres):
                    altres[alt_idx] = value
                else:
                    self._send_json({"status": "error", "error": "Índice inválido"}); return
                _patch_question(settings, sb_id, {"resolucoes_alternativas": altres})
                self._send_json({"status": "ok"})
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

        def _handle_ai_review(self, payload: dict) -> None:
            self._send_json({
                "status": "error",
                "error": "Revisão por IA via API foi descontinuada. "
                         "Use o agente Claude Code para rever questões directamente.",
            })

        def _handle_patch_header(self, payload: dict) -> None:
            sb_id = payload.get("sb_id", "")
            allowed = {"id_item", "tipo_item", "resposta_correta"}
            update = {k: v for k, v in payload.items() if k in allowed}
            if not update:
                self._send_json({"status": "error", "error": "Nenhum campo válido"})
                return
            try:
                _patch_question(settings, sb_id, update)
                self._send_json({"status": "ok"})
            except Exception as exc:
                self._send_json({"status": "error", "error": str(exc)})

    return _Handler


class _ReuseServer(socketserver.TCPServer):
    allow_reuse_address = True


def run_supabase_preview(
    settings: Settings,
    port: int = 8797,
    fonte: str | None = None,
) -> str:
    """Inicia o servidor de preview editável puxando do Supabase."""
    if not settings.supabase_url or not settings.supabase_key:
        raise ValueError("SUPABASE_URL e SUPABASE_KEY não configurados no .env")

    handler = _make_handler(settings)
    url = f"http://localhost:{port}"
    if fonte:
        url += f"?fonte={urllib.parse.quote(fonte)}"

    with _ReuseServer(("localhost", port), handler) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        print(f"[supabase-preview] Servidor em {url}")
        print("[supabase-preview] Ctrl+C para parar.")
        webbrowser.open(url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            print("\n[supabase-preview] A parar o servidor...")
        finally:
            httpd.shutdown()

    return url
