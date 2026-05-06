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

## 5. Integridade do Documento Original

**O texto da prova é sagrado. Nunca inventes, parafraseies ou "melhores" conteúdo original.**

A revisão do `prova.md` e do `questoes_review.json` é **transcrição com correção de artefatos OCR** — não é uma tarefa de redação, tradução ou interpretação. O agente não é o autor do texto.

### O que é permitido

| Tipo de edição | Condição obrigatória |
|---------------|----------------------|
| Corrigir tipografia PT (`«»`, `…`, diacríticos) | O erro é inequívoco (ex: `"` → `«»`) |
| Converter número fundido → sobrescrito (`palavra2` → `palavra²`) | Automático via pipeline; nunca deduzir o número |
| Corrigir ordinal OCR → sobrescrito (`cútisº` → `cútis⁸`) | O número correto está **explicitamente listado nas NOTAS** do próprio documento |
| Corrigir hífens de quebra de linha | O erro é inequívoco |

### O que é proibido — hard stops

- **Nunca alterar definições nas NOTAS** (secção "NOTAS" do excerto). As definições são transcritas do PDF; o agente não tem autoridade para as corrigir, clarificar ou expandir.
- **Nunca deduzir um número de nota por raciocínio** (ex: "a nota 9 cobre Antony e Fausto, logo Fausto deve ser ⁹"). Se os números não batem certo, assinalar e parar.
- **Nunca preencher lacunas** no texto original — se o OCR perdeu uma palavra ou frase, marcar com `[ILEGÍVEL]` e reportar ao utilizador. Não inventar o que podia estar lá.
- **Nunca remover lacunas intencionais do enunciado** (espaços sublinhados `_____`, traços longos `———`, ou sequências equivalentes que representam o local onde o aluno deve preencher). São parte da formulação do exame em itens de completar (`complete_table`, frases-lacuna do GRUPO II, etc.). Se o OCR transcreveu a lacuna como `_____`, `\_\_\_\_`, `——` ou similar, **manter exatamente** — converter apenas para uma forma canónica consistente (ex.: `_____` com 5 underscores) sem suprimir.
- **Nunca reescrever frases** do enunciado ou das NOTAS para as tornar mais claras ou gramaticalmente corretas. Mesmo que pareça errado, pode ser a formulação exata do exame.
- **Nunca usar o conhecimento geral** sobre a obra, o autor ou o tema para "completar" ou "corrigir" o texto. O PDF é o árbitro — o agente não leu o PDF.

### Regra de ouro

> Se não consegues apontar no próprio documento a evidência que justifica a alteração, não faças a alteração.

Quando em dúvida: reportar ao utilizador com a linha exata e o motivo da dúvida.

---

## Contexto do projeto

Pipeline Python para extrair, validar, categorizar e publicar questões de provas de exames nacionais de **Português** (Exame Nacional 639) → Supabase/PostgreSQL.

**Princípio fundamental:** nenhum módulo faz chamadas a APIs externas de LLM. Todo o trabalho de inteligência (revisão, categorização, extração de critérios, correção OCR) é feito pelo agente diretamente via ferramentas Read + Edit.

**Repositório:** `Blackcoffee111/extrator-de-questoes` (fork dedicado a Português)  
**PIPELINE_ROOT:** `/Users/adrianoushinohama/dev/Exames Nacionais/Provas de portugues`

---

## Python e ambientes

| Uso | Binário |
|-----|---------|
| Pipeline (módulos 1–7) | `/opt/homebrew/bin/python3.11` |
| MinerU CLI | `/Users/adrianoushinohama/dev/Exames Nacionais/Provas de matemática/.venv-mineru/bin/mineru` (Python 3.12) |

⚠️ **O `.venv-mineru` NÃO está em `Provas de portugues`** — está partilhado em `Provas de matemática` (a pasta-irmã). Usar sempre o caminho absoluto. `.venv-mineru/bin/mineru` (relativo) falha com `no such file or directory`.

⚠️ Nunca usar `/opt/homebrew/bin/python3` — é 3.14, sem as dependências instaladas.

---

## MinerU — sintaxe e restrições

```bash
MINERU="/Users/adrianoushinohama/dev/Exames Nacionais/Provas de matemática/.venv-mineru/bin/mineru"
"$MINERU" -b pipeline -p "provas fonte/<prova>.pdf" -o "workspace/<workspace>"
```

- Sempre `-b pipeline` (CPU). GPU consome toda a RAM do M1 Air 8 GB e falha.
- Usar `-p` para o PDF (não `-i`). Para Português: **não usar `-l en`** (prejudica diacríticos PT). Usar apenas `-m ocr` se necessário.
- **MinerU deve correr fora do sandbox.** Se `run_stage(stage='extract')` falhar, correr no Terminal, copiar `prova.md` + `images/` para o workspace, e chamar `run_stage(stage='extract')` sem `pdf_path`.

---

## Superfície MCP — 7 tools

O agente usa apenas estes 6 comandos. Tudo o resto (micro-lint, cotações, cc_extract, cc_validate, cc_merge, backup) corre internamente.

| Tool | Descrição |
|------|-----------|
| `list_workspaces()` | Lista todos os workspaces e estado resumido |
| `workspace_status(workspace)` | Estado detalhado + próxima acção sugerida — **usar sempre que em dúvida** |
| `run_stage(workspace, stage, ...)` | Executa um estágio do pipeline |
| `run_review(workspace)` | Abre preview para revisão humana |
| `run_fix_question(workspace, id_item, field, value)` | Correção pontual pós-revisão |
| `get_question_context(workspace, id_item, pad=3)` | Extrato do prova.md para um item (verificar OCR sem ler o ficheiro inteiro) |
| `get_context_stem_pdf_pages(workspace, id_item)` | PDF + páginas prováveis de um `context_stem` — para verificação obrigatória dos números de linha |

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

## Referência paralela `prova_pymupdf.md`

Sempre que `run_stage(stage='extract', pdf_path=...)` corre, é disparado em background um extractor PyMuPDF que grava `prova_pymupdf.md` no workspace. Termina antes do MinerU.

- **NÃO é o ficheiro a editar.** O ficheiro canónico continua a ser `prova.md` (do MinerU, com imagens/tabelas/estrutura).
- **Use como segunda fonte** durante a revisão de `prova.md` quando o OCR parecer suspeito: diacríticos esquisitos, sobrescritos perdidos (`palavra2` em vez de `palavra²`), ordinais (`cútisº`), números fundidos, parênteses corrompidos.
- PyMuPDF lê a **camada de texto nativa** do PDF — não faz OCR. Se o PDF tem texto embutido (caso comum nos exames IAVE), os caracteres são exactos. Onde diverge do `prova.md`, em ~95% dos casos PyMuPDF está certo.
- **Não copiar cegamente:** PyMuPDF não preserva imagens, tabelas, cabeçalhos markdown nem ordem de leitura multi-coluna. Ler ambos e decidir trecho a trecho.
- Se `prova_pymupdf.md` não existir (PDF sem camada de texto, ou PyMuPDF falhou silenciosamente), consultar `prova_pymupdf.log` no workspace.

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
3. Preencher `tema`, `subtema`, `descricao_breve`, `tags` inline — **inclusive para `context_stem`**
4. Para `essay`: preencher `palavras_min` e `palavras_max` se visível no enunciado
5. Setar `"reviewed": true` no item após revisar
6. Para verificar o OCR bruto de um item: `get_question_context(workspace, id_item)` — devolve o extrato do `prova.md` sem ler o ficheiro inteiro

**Categorização granular (obrigatória):** não escrever `tema` / `subtema` genéricos como `"Narrativa"` / `"Coração, Cabeça e Estômago"`. Usar a forma `"<Domínio> — <Género/Subdomínio>"` no tema e `"<Autor>, «<Obra>» — <recorte específico>"` no subtema. Ver o catálogo completo no skill `/exames`, secção 4.1.

**Itens `context_stem` em provas de Português** (id_item do tipo `"I-ctx1"`, `"I-ctx2"`, `"II-ctx1"`, `"III-ctx1"`):
- Representam o excerto literário (GRUPO I), texto expositivo (GRUPO II) e tema de dissertação (GRUPO III)
- Revisão obrigatória: tipografia PT («», …, diacríticos), numeração de linhas do excerto, notas de rodapé
- **Categorização obrigatória**: `tema`, `subtema`, `descricao_breve`, `tags` seguem o mesmo critério granular das questões (ver skill `/exames`, secção 4.2).
<!-- DESACTIVADO 2026-05-05 — em teste o fluxo PyMuPDF-only. A leitura directa de PDFs com Read está bloqueada por hook (.claude/hooks/block_pdf_read.py).
- **Sempre que o stem contém texto literário, poema, prosa ou outro excerto, abrir o PDF é obrigatório** — não confiar só no markdown do MinerU. Usar `get_context_stem_pdf_pages(workspace, id_item)` para localizar o PDF e o intervalo de páginas, e depois `Read(file_path=<pdf>, pages=...)`. Verificar e corrigir, em conjunto:
-->
- **Verificar texto literário/poema/prosa contra o PDF — apenas via PyMuPDF (`fitz`)**, nunca com a tool `Read` (bloqueada por hook). Usar `get_context_stem_pdf_pages(workspace, id_item)` para localizar PDF e intervalo de páginas, e depois extrair só o que precisa via Bash:

  ```bash
  /opt/homebrew/bin/python3.11 -c "import fitz; doc=fitz.open('CAMINHO.pdf'); \
  print(doc[N-1].get_text())"   # N = página 1-indexed
  ```

  Verificar e corrigir, em conjunto:
  1. **Números de linha** na margem do excerto (mesmo fluxo descrito a seguir).
  2. **Formatação** — itálico (citações, palavras estrangeiras, ênfase), negrito, separação estrófica nos poemas, recuos, espaçamentos entre parágrafos. Se o MinerU perdeu, repor com markdown (`*itálico*`, `**negrito**`, linha em branco entre estrofes/parágrafos).
  3. **Números sobrescritos** que marcam notas de rodapé (`palavra²`, `cútis⁸`). O OCR frequentemente entrega `palavra2`, `cutisº`, `cútis8`. Confirmar o número exacto contra o PDF e converter para o caractere sobrescrito Unicode (`²³⁴⁵⁶⁷⁸⁹`). **Nunca deduzir o número** — se o PDF não permite ver com certeza, marcar `[VERIFICAR]` e parar.
  4. **Legendas e rodapé/notas** — o bloco "NOTAS" (ou equivalente) que define os termos marcados. Confirmar (a) numeração das notas bate com os sobrescritos no texto, (b) o texto da definição é transcrito literalmente do PDF, sem reescrever. Reportar incoerências em vez de "corrigir" silenciosamente.
- **Verificação obrigatória de números de linha** — gate duro no `validate`:
  1. Para cada `context_stem`, chamar `get_context_stem_pdf_pages(workspace, id_item)` — devolve o PDF, o intervalo de páginas provável e o excerto actual de `prova.md`.
  2. Extrair o texto dessas páginas com PyMuPDF via Bash (`/opt/homebrew/bin/python3.11 -c "import fitz; doc=fitz.open('...'); print(doc[N-1].get_text())"`) e contar os marcadores de linha na margem do excerto. **Não usar `Read` em PDFs — está bloqueado por hook.**
  3. Editar o `enunciado` em `questoes_review.json` aplicando o **formato canónico**: cada marcador fica sozinho em início de linha, no padrão `\n{N} {conteúdo da linha N}`. Nunca deixar um número fundido à palavra seguinte, nem inline no meio de uma frase, nem com OCR corrompido (`|0`, `I0`, `l0`, `IO`) — reescrever para o dígito canónico.
     ⚠️ **Apenas os marcadores impressos na margem do PDF.** Nas provas IAVE o excerto é numerado **só nos múltiplos de 5** (`5`, `10`, `15`, `20`, …). **Nunca** numerar linha a linha (`1`, `2`, `3`, `4`, …) — isso é fabricar marcadores que não existem no original e contamina os enunciados que citam «(linha 9)», «(linha 13)», etc. Se o PDF mostra `5`, `10`, `15` na margem, o `enunciado` tem exactamente esses três marcadores, não mais. Se a 1.ª linha do excerto não tem marcador no PDF, **não** prefixar com `1`.
  4. Preencher `tem_numeracao_linhas`: `true` se o excerto original no PDF tem marcadores de linha; `false` se não tem (ex.: tema de dissertação do Grupo III, tipicamente sem numeração).
  5. Se `tem_numeracao_linhas: false`, garantir que nenhum dígito espúrio do OCR ficou colado a palavras — limpar antes de prosseguir.
  6. Marcar `linhas_verificadas: true` apenas depois de (2)+(3)+(4) estarem completas.
- `run_stage(stage='validate')` **bloqueia** se qualquer `context_stem` tem `tem_numeracao_linhas: null`, `linhas_verificadas: false`, marcadores ausentes quando `tem_numeracao_linhas: true`, ou resíduos numéricos quando `tem_numeracao_linhas: false`.
- Setar `"reviewed": true` depois de verificar o texto, preencher a categorização e completar o fluxo acima — idêntico às questões regulares

`run_stage(stage='validate')` faz o merge de `questoes_review.json` + `questoes_meta.json` antes do lint.  
`run_stage(stage='validate')` bloqueia se existirem itens com `"reviewed": false`.  
O mesmo contrato aplica-se a `criterios_raw.json` no fluxo CC-VD (sem categorização).

**Relação pai ↔ filha (`ids_contexto_pai` / `id_contexto_pai`) — obrigatório em provas PT:**
- Em provas de Português, cada Parte (A/B/C) ou Grupo com texto-âncora tem um único `context_stem` pai das questões daquela parte. Ex.: em 2024, **um texto serve toda a Parte A, outro toda a Parte B**, e assim por diante.
- **Campo canónico:** `ids_contexto_pai: list[str]` — lista de IDs de stems pai. A maioria das questões tem 1 elemento. Excepção: questões que comparam múltiplos textos (ex.: `I-C-7` da Parte C, que pede para comparar Parte A com Parte B) — preencher com **todos** os ids referenciados, ex.: `["I-ctx1","I-ctx2"]`.
- **Campo legado:** `id_contexto_pai: str` — string com o primeiro pai. Mantido para retrocompat. Quando preenches `ids_contexto_pai`, o pipeline deriva `id_contexto_pai` automaticamente. Para questões com pai único basta editar qualquer um dos dois.
- O extractor preenche `id_contexto_pai`/`ids_contexto_pai` automaticamente quando deteta o preâmbulo da parte. Mesmo assim, o `validate` corre um gate anti-órfãs:
  - **ERRO (bloqueia)**: questão com lista vazia **e** existe um `context_stem` na mesma `(grupo, parte)`. O agente tem de abrir `questoes_review.json`, ler o enunciado para confirmar a referência, e preencher `ids_contexto_pai` com o(s) id(s) do(s) stem(s).
  - **AVISO**: questão órfã cujo grupo tem stems em partes diferentes (ex.: `I-C-7`). Ler o enunciado: se referencia 1 texto, preencher com `["<id>"]`; se compara 2+ textos, preencher com a lista completa (ex.: `["I-ctx1","I-ctx2"]`); se nenhum, deixar vazio.
- **Renderização:** questões com 2+ pais são anexadas após o ÚLTIMO pai (em ordem de documento), com badge visual `🔗 N contextos` no cabeçalho.
- **Upload Supabase:** com 2+ pais, o pipeline cria automaticamente um *contexto sintético* na BD agregando os textos dos stems referenciados. O frontend continua vendo um único contexto seguido da questão.
- Para corrigir pós-validate: `run_fix_question(workspace, id_item="I-C-7", field="ids_contexto_pai", value='["I-ctx1","I-ctx2"]')`.

---

## `cotacoes_estrutura.json` — manifesto estrutural obrigatório

O ficheiro declara o **conjunto canónico de IDs do exame** extraído da secção `# COTAÇÕES` do `prova.md`. O que importa são as chaves (estrutura), não os pontos — em PT os pontos são uniformes (13/44), o que muda entre anos é a estrutura (Partes A/B/C, pools opcionais, fusões).

### Formato canónico (estrito)

```json
{
  "total_itens_principais": 15,
  "estrutura": {"I-A-1": [], "I-A-2": [], "...": []},
  "cotacoes": {"I-A-1": 13, "I-A-2": 13, "...": 13, "III-1": 44},
  "confianca": "alta",
  "raw_response": "",
  "pool_opcional": [
    {"pontos": 39, "itens": ["I-A-3", "I-B-6", "II-2", "II-3", "II-5"], "escolher": 3}
  ],
  "bypass_validation": false,
  "bypass_motivo": ""
}
```

- Chaves com prefixo de grupo: `"I-1"`, `"I-A-1"`, `"II-2"`, `"III-1"` (nunca `"1"`, `"I"`, `"II"`).
- Pool opcional: lista de pools, cada um com `pontos` (total da nota), `itens` (IDs candidatos) e `escolher` (quantos contam). Itens declarados em pool **devem** estar também em `cotacoes`/`estrutura` — são itens reais do exame; o pool só restringe quais contam para a nota.

### Gates duros do `validate`

`run_stage(stage='validate')` aborta com erro se:
- O ficheiro **não existe** (`FileNotFoundError`).
- O ficheiro está em formato legado (mapa plano `{"I-1": 13}` ou stub `{"I-1": {"pontos": null}}`) — a mensagem aponta para `scratch/migrate_cotacoes.py`.
- `confianca` é `"ausente"` ou `cotacoes` está vazio.
- `bypass_validation: true` mas `bypass_motivo` vazio.

### Quando o parser falha

`run_stage(stage='extract')` **não cria stub silencioso**. Se a tabela COTAÇÕES estiver como imagem ou com OCR corrompido, o output diz exactamente o que fazer:
1. Abrir o PDF na página da tabela.
2. Criar manualmente `cotacoes_estrutura.json` no formato canónico acima.
3. Re-correr `run_stage(stage='validate')`.

### Bypass auditável

Se for genuinamente impossível extrair cotações (e.g. página corrompida sem alternativa), criar o ficheiro com:
```json
{"cotacoes": {...itens conhecidos...}, "bypass_validation": true, "bypass_motivo": "<porquê>"}
```
O `bypass_motivo` é obrigatório — desliga o cross-check estrutura↔JSON mas mantém todas as outras validações por item.

### Migração de ficheiros legados

```
python scratch/migrate_cotacoes.py                # migra todos os workspaces
python scratch/migrate_cotacoes.py <path>         # migra um ficheiro específico
```

---

## Verificação `criterios_raw.json` — após 1ª chamada `run_stage(stage='cc')`

### Onde ler — `prova.md` do workspace CC, não o PDF

O extractor já corta o markdown na âncora `# CRITÉRIOS ESPECÍFICOS DE CLASSIFICAÇÃO` e descarta tudo o que vem antes. **Não tentar ler o PDF do CC-VD para preencher campos que já estão no markdown.** Se algo parece em falta, ler primeiro `workspace/<NOME>-CC-VD_net/prova.md` — o MinerU já transcreveu o texto, incluindo tabelas. O PDF é último recurso (e.g. assinatura/imagem que o MinerU não conseguiu transcrever).

### O que **ignorar sempre** no CC-VD de Português

São conteúdo genérico, repetido em todas as provas — não copiar, não transcrever, não tentar ler do PDF:

1. **Critérios Gerais de Classificação** — primeiras ~3 páginas do PDF. Preâmbulo legal/operacional do IAVE; o extractor já as descarta automaticamente cortando na âncora `# CRITÉRIOS ESPECÍFICOS DE CLASSIFICAÇÃO`.
2. **Tabela CL ("Aspectos de correção linguística")** — grelha 3 pontos baseada em erros tipo A / tipo B. É o mesmo template em todos os anos; o pipeline já a cobre via `parametros_classificacao`.

### Tabela C-ED — capturar **apenas o descritor do nível máximo** via PyMuPDF

A tabela "Aspectos de conteúdo e de estruturação do discurso (C-ED)" tem **descritores específicos** de cada questão — não é genérica como a CL. Mas só o **descritor do nível com pontuação máxima** (tipicamente Nível 5 / 10 pontos) deve ser capturado; os níveis intermédios são derivados.

O MinerU pode não preservar a estrutura tabular fielmente. Usar **PyMuPDF (`fitz`)** para extrair o texto directamente do PDF do CC-VD na página onde está a tabela:

```python
import fitz
doc = fitz.open("provas fonte/.../EX-Port639-...-CC.pdf")
page = doc[N - 1]   # N = página da tabela C-ED do item (1-indexed → 0-indexed)
text = page.get_text()
# Localizar o bloco entre "Níveis" e a linha "4" (ou "OU") — é o descritor do Nível 5
```

Colocar o texto extraído num único `criterios_parciais` da questão essay (ou no campo apropriado), com `pontos` igual à pontuação máxima indicada na bullet ("10 pontos" no exemplo). **Não copiar os níveis 4–1** nem a tabela inteira.

Se o agente encontrar a tabela CL ou descritores intermédios da C-ED a contaminar `solucao`/`criterios_parciais`, **apagar** — deixar só o descritor do nível máximo.

### Como ler a chave de respostas do GRUPO II (MC)

A tabela "GRUPO II / ITENS / CHAVE DE RESPOSTA / PONTUAÇÃO" (e a equivalente para a Parte A do GRUPO I em provas com partes) está no `prova.md` do workspace CC como tabela markdown. **Ler de lá, nunca do PDF**:

```
Read("workspace/<NOME>-CC-VD_net/prova.md")
# Procurar pelo bloco "GRUPO II" / "CHAVE DE RESPOSTA" e extrair as letras
```

Mapear cada linha (`1. → C`, `2. → A`, …) ao `id_item` correspondente em `criterios_raw.json` e preencher `resposta_correta`. **Apagar** qualquer letra herdada do extractor automático que não bata com o markdown — a tabela na imagem é a fonte de verdade, não o output regex do extractor.

### Espelhar `solucao` em `criterios_parciais`

Para questões de resposta extensa (`open_response`, `essay`), depois de preencher `solucao` (a "Resolução completa" / resposta esperada), **copiar o mesmo texto também para `criterios_parciais`** como descrição do critério principal (tipicamente o do nível de pontuação máxima da C-ED).

Motivo: o preview e o Supabase mostram os dois campos por caminhos diferentes — `solucao` aparece no painel "Ver resolução completa", `criterios_parciais` aparece nos critérios de classificação. O classificador humano deve ver o conteúdo da resolução em ambos os sítios; deixar `criterios_parciais` vazio ou só com o descritor genérico C-ED esconde a resposta esperada do utilizador final.

Padrão para questões essay com tabela C-ED:

```json
"solucao": "<texto integral da resolução completa>",
"criterios_parciais": [
  {
    "nivel": "5",
    "pontos": 10,
    "descricao": "<descritor C-ED do Nível 5> + <texto integral da resolução completa>"
  }
]
```

Não duplicar quando o `solucao` é trivial (ex.: MC só com a letra correcta). Aplica-se sempre que `solucao` contém texto explicativo/argumentativo.

### Outras verificações

1. **Itens com 0 etapas:** extrair manualmente do `bloco_ocr` ou do `prova.md` (não do PDF).
2. **Duplicados `II-*`:** se existirem entradas `II-1` (pending) e `1` (parsed), apagar as prefixadas.
3. **Cobertura integral dos `criterios_parciais`:** O extractor agrega automaticamente o texto do 1.º Processo à `descricao` do último step top-level. Verificar que a `descricao` desse step contém: (a) descrição curta, (b) texto de transição se presente, (c) texto integral do 1.º Processo com todos os sub-passos. **Nunca encurtar nem parafrasear** — se truncado, restaurar do `texto_original`.

---

## Para processar uma prova

Invocar o skill `/exames` — contém o checklist completo de cada fase, o catálogo de erros OCR a corrigir no `prova.md`, e o fluxo CC-VD.
