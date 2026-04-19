## Contexto do projeto

Pipeline Python para extrair, validar, categorizar e publicar questões de provas de exames nacionais de Matemática A (Portugal) → Supabase/PostgreSQL.

**Princípio fundamental:** nenhum módulo faz chamadas a APIs externas de LLM. Todo o trabalho de inteligência (revisão, categorização, extração de critérios, correção OCR) é feito pelo agente diretamente via ferramentas Read + Edit.

**Repositório:** `Blackcoffee111/extrator-de-questoes`  
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
- Usar `-p` para o PDF (não `-i`). Flags úteis: `-m ocr` (PDFs de imagem), `-l en` (melhora LaTeX).
- **MinerU deve correr fora do sandbox.** Se `run_stage(stage='extract')` falhar, correr no Terminal, copiar `prova.md` + `images/` para o workspace, e chamar `run_stage(stage='extract')` sem `pdf_path`.

---

## Superfície MCP — 5 tools

O agente usa apenas estes 5 comandos. Tudo o resto (micro-lint, cotações, cc_extract, cc_validate, cc_merge, backup) corre internamente.

| Tool | Descrição |
|------|-----------|
| `list_workspaces()` | Lista todos os workspaces e estado resumido |
| `workspace_status(workspace)` | Estado detalhado + próxima acção sugerida — **usar sempre que em dúvida** |
| `run_stage(workspace, stage, ...)` | Executa um estágio do pipeline |
| `run_review(workspace)` | Abre preview para revisão humana |
| `run_fix_question(workspace, id_item, field, value)` | Correção pontual pós-revisão |

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
  → revisão prova.md                [agente: Read + Edit]
  → revisão questoes_raw.json       [agente: Read + Edit — reviewed:true + categorização inline]
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
| Revisão questões + categorização | **Agente** | Read + Edit em `questoes_raw.json` |
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

## Contrato de revisão em `questoes_raw.json`

Cada item gerado pelo `run_stage(stage='extract')` tem `"reviewed": false`. O agente deve:
1. Ler `questoes_raw.json` com `Read`
2. Para cada item: verificar enunciado, alternativas, LaTeX, imagens; corrigir com `Edit`
3. Preencher `tema`, `subtema`, `descricao_breve`, `tags` inline (exceto `context_stem`)
4. Setar `"reviewed": true` no item após revisar

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

---

## Para processar uma prova

Invocar o skill `/exames` — contém o checklist completo de cada fase, o catálogo de erros OCR a corrigir no `prova.md`, e o fluxo CC-VD.
