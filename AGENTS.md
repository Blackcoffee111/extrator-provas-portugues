Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.



## Contexto do projeto

Pipeline Python para extrair, validar, categorizar e publicar questões de provas de exames nacionais de **Português** (Exame Nacional 639) → Supabase/PostgreSQL.

**Princípio fundamental:** nenhum módulo faz chamadas a APIs externas de LLM. Todo o trabalho de inteligência (revisão, categorização, extração de critérios, correção OCR) é feito pelo agente diretamente via ferramentas Read + Edit.

**Repositório:** `Blackcoffee111/extrator-de-questoes` (fork dedicado a Português)  
**PIPELINE_ROOT:** `/Users/adrianoushinohama/Desktop/Exames Nacionais`

---

## Python e ambientes

| Uso | Binário |
|-----|---------|
| Pipeline (módulos 1–7) | `/opt/homebrew/bin/python3.11` |
| MinerU CLI | `.venv-mineru/bin/mineru` (Python 3.12) |

⚠️ Nunca usar `/opt/homebrew/bin/python3` — é 3.14, sem as dependências instaladas.

---

## MinerU — sintaxe e restrições

```bash
.venv-mineru/bin/mineru -b pipeline -p "provas fontes/<prova>.pdf" -o workspace/<workspace>
```

- Sempre `-b pipeline` (CPU). GPU consome toda a RAM do M1 Air 8 GB e falha.
- Usar `-p` para o PDF (não `-i`). Para Português: **não usar `-l en`** (prejudica diacríticos PT). Usar apenas `-m ocr` se necessário.
- **MinerU deve correr fora do sandbox.** Se `run_stage(stage='extract')` falhar, correr no Terminal, copiar `prova.md` + `images/` para o workspace, e chamar `run_stage(stage='extract')` sem `pdf_path`.

---

## Superfície MCP — 6 tools

O agente usa apenas estes 6 comandos. Tudo o resto (micro-lint, cotações, cc_extract, cc_validate, cc_merge, backup) corre internamente.

| Tool | Descrição |
|------|-----------|
| `list_workspaces()` | Lista todos os workspaces e estado resumido |
| `workspace_status(workspace)` | Estado detalhado + próxima acção sugerida — **usar sempre que em dúvida** |
| `run_stage(workspace, stage, ...)` | Executa um estágio do pipeline |
| `run_review(workspace)` | Abre preview para revisão humana |
| `run_fix_question(workspace, id_item, field, value)` | Correção pontual pós-revisão |
| `get_question_context(workspace, id_item, pad=3)` | Extrato do prova.md para um item (verificar OCR sem ler o ficheiro inteiro) |

### Stages de `run_stage`

| Stage | O que faz internamente | Requer | Define |
|-------|------------------------|--------|--------|
| `extract` | MinerU + cotações + estruturação | `fresh` (ou `prova.md` já presente) | `extracted` |
| `validate` | micro-lint → validação heurística | `extracted` + todos `reviewed:true` | `validated` |
| `cc` | 1ª chamada: cc_extract; 2ª chamada: cc_validate | `prova.md` no workspace CC | CC `cc_extracted` / `cc_validated` |
| `merge` | cc_merge + abre preview | `validated` + CC `cc_validated` + todos categorizados | `cc_merged` |
| `upload` | upload Supabase + backup automático | `human_approved` | `uploaded` |

---

## Fluxo obrigatório (linear, unidirecional)

```
MinerU (Terminal, fora do sandbox)
  → run_stage(stage='extract')
  → revisão prova.md                [agente: Read + Edit — ou get_question_context() para itens pontuais]
  → revisão questoes_review.json    [agente: Read + Edit — reviewed:true + categorização inline]
  → run_stage(stage='validate')     [micro-lint + validação — internos]
  → MinerU CC-VD (Terminal)
  → run_stage(stage='cc')           [1ª chamada: cc_extract]
  → revisão criterios_raw.json      [agente: Read + Edit — reviewed:true]
  → run_stage(stage='cc')           [2ª chamada: cc_validate]
  → run_stage(stage='merge')        [cc_merge + preview]
  → run_review(workspace)           [humano: botão "✅ Aprovar para Upload"]
  → run_stage(stage='upload')       [upload + backup]
```

| Fase | Responsável | Ferramenta |
|------|-------------|------------|
| OCR | CLI manual | — |
| Revisão `prova.md` | **Agente** | Read + Edit |
| Revisão questões + categorização | **Agente** | Read + Edit em `questoes_review.json` |
| Lint + validação | MCP (interno) | `run_stage(stage='validate')` |
| Critérios CC-VD | MCP + **Agente** | `run_stage(stage='cc')` × 2 → revisão → `run_stage(stage='merge')` |
| Aprovação final | **Humano** | `run_review` |
| Upload | MCP (interno) | `run_stage(stage='upload')` |

---

## Máquina de estados por workspace

Cada workspace tem um `state.json` que impõe a progressão — os stages recusam automaticamente operações fora de ordem.

**Estados do pipeline principal:**
```
fresh → extracted → validated → cc_merged → human_approved → uploaded
```

**Estados do sub-pipeline CC-VD** (workspace CC separado):
```
cc_fresh → cc_extracted → cc_validated
```

`human_approved` é definido automaticamente quando o humano clica "✅ Aprovar" no preview (cria `.review_approved`).

Workspaces antigos (sem `state.json`) têm o estado inferido a partir dos ficheiros existentes — retrocompatível.

---

## Estrutura das provas de Português (Exame 639)

| Grupo | Conteúdo | Tipos de item |
|-------|----------|---------------|
| **GRUPO I** | Excerto literário + Parte A/B/C | `multiple_choice` (Parte A), `open_response` (Parte B/C) |
| **GRUPO II** | Texto expositivo/argumentativo | `open_response`, `complete_table`, `multi_select` |
| **GRUPO III** | Produção escrita (dissertação) | `essay` |

**IDs:** `grupo="I"` + `id_item="A-1"` (Parte A, item 1); `id_item="B-3"` (Parte B, item 3); `id_item="III-1"` (Grupo III sem partes).

**Tipos especiais:**
- `essay` — dissertação; requer `palavras_min`/`palavras_max`; CC tem `criterios_parciais` com `{nivel, pontos, descricao}`.
- `complete_table` — completar lacunas numa tabela; requer imagem ou tabela MD no enunciado.
- `multi_select` — assinalar V/F em afirmações numeradas (I, II, III…).
- `pool_opcional` — itens do mesmo pool (e.g. `"pool_II_opcional"`) onde o aluno escolhe X de Y.

**Tipografia PT obrigatória no `prova.md`:** «» para citações, … para reticências, diacríticos corretos, numeração de linhas do excerto sem espaço prefixado.

**Sem LaTeX** — não usar `$...$` nem `\[...\]`. MathJax desativado no preview PT.

---


## Contrato de revisão em `questoes_review.json`

Cada item gerado pelo `run_stage(stage='extract')` tem `"reviewed": false`. O agente deve:
1. Ler `questoes_review.json` com `Read` (ficheiro compacto — sem `texto_original`, `source_span` e campos estruturais)
2. Para cada item: verificar enunciado, tipografia PT, imagens; corrigir com `Edit`
3. Preencher `tema`, `subtema`, `descricao_breve`, `tags` inline (exceto `context_stem`)
4. Para `essay`: preencher `palavras_min` e `palavras_max` se visível no enunciado
5. Setar `"reviewed": true` no item após revisar
6. Para verificar o OCR bruto de um item: `get_question_context(workspace, id_item)` — devolve o extrato do `prova.md` sem ler o ficheiro inteiro

`run_stage(stage='validate')` faz o merge de `questoes_review.json` + `questoes_meta.json` antes do lint.  
`run_stage(stage='validate')` bloqueia se existirem itens com `"reviewed": false`.  
O mesmo contrato aplica-se a `criterios_raw.json` no fluxo CC-VD (sem categorização).

---

## Verificação `cotacoes_estrutura.json` — após `run_stage(stage='extract')`

Confirmar formato correto antes de `run_stage(stage='validate')`:
- ✅ Correto: `"I-1"`, `"II-2.1"` (prefixo de grupo incluído na chave)
- ❌ Errado: `"I"`, `"II"` como chaves pai sem número de item

Se errado, corrigir com `Edit` antes de continuar.

---

## Verificação `criterios_raw.json` — após 1ª chamada `run_stage(stage='cc')`

1. **GRUPO I (MC):** gabarito está numa imagem → ler com `Read` o PDF e preencher `resposta_correta` manualmente.
2. **Itens com 0 etapas:** extrair manualmente do `bloco_ocr` ou do PDF com `Edit`.
3. **Duplicados `II-*`:** se existirem entradas `II-1` (pending) e `1` (parsed), apagar as prefixadas.
4. **Cobertura integral dos `criterios_parciais`:** O extractor agrega automaticamente o texto do 1.º Processo à `descricao` do último step top-level. Verificar que a `descricao` desse step contém: (a) descrição curta, (b) texto de transição se presente, (c) texto integral do 1.º Processo com todos os sub-passos. **Nunca encurtar nem parafrasear** — se truncado, restaurar do `texto_original`.

---

## Para processar uma prova

Invocar o skill `/exames` — contém o checklist completo de cada fase, o catálogo de erros OCR a corrigir no `prova.md`, e o fluxo CC-VD.
