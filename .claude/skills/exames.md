# Skill: exames

Processa uma prova de exame nacional: OCR → revisão → validação → critérios CC-VD → upload.

## Quando usar

Invocar com `/exames` para:
- Verificar ambiente e configuração MCP
- Processar um PDF de prova do zero
- Retomar uma prova em qualquer fase

---

## 1. Verificar ambiente

```bash
PIPELINE_ROOT="/Users/adrianoushinohama/dev/Exames Nacionais/Provas de portugues"
MINERU_BIN="/Users/adrianoushinohama/dev/Exames Nacionais/Provas de matemática/.venv-mineru/bin/mineru"

/opt/homebrew/bin/python3.11 -c "import mcp, pymupdf, supabase; print('✅ deps ok')" 2>&1
"$MINERU_BIN" --version 2>&1
ls $PIPELINE_ROOT/.env && echo "✅ .env presente" || echo "❌ .env ausente"
```

⚠️ O `.venv-mineru` **não vive em `Provas de portugues`** — está partilhado em `Provas de matemática` (pasta-irmã). Usar sempre o caminho absoluto acima. `.venv-mineru/bin/mineru` (relativo) falha com `no such file or directory`.

Se as tools `mcp__exames-pipeline__*` estiverem disponíveis, o servidor MCP está ativo.
Se não estiverem, instruir o utilizador a reiniciar o Claude Code.

Usar `workspace_status(workspace)` sempre que em dúvida sobre o estado de um workspace.

---

## 2. Executar MinerU (fora do sandbox)

> ⚠️ MinerU falha em ambientes sandbox (multiprocessing bloqueado). Pedir ao utilizador para correr no Terminal:

```bash
cd "/Users/adrianoushinohama/dev/Exames Nacionais/Provas de portugues"
MINERU="/Users/adrianoushinohama/dev/Exames Nacionais/Provas de matemática/.venv-mineru/bin/mineru"
"$MINERU" -b pipeline -p "provas fonte/PROVA.pdf" -o "workspace/NOME"
# Localizar e copiar o .md gerado:
find workspace/NOME -name "*.md" | head -1
cp <caminho_encontrado> workspace/NOME/prova.md
cp -r workspace/NOME/NOME/pipeline/images/ workspace/NOME/images/
```

Após o utilizador confirmar que o MinerU terminou, chamar:

```
run_stage(workspace="NOME", stage="extract")
```

> Se `pdf_path` for fornecido, `run_stage(stage='extract')` tenta correr MinerU internamente.  
> Se `prova.md` já existir no workspace (MinerU manual), re-estrutura sem re-correr OCR.

Verificar e corrigir `cotacoes_estrutura.json` antes de avançar:
- ✅ Correto: `"I-1"`, `"II-2.1"` (prefixo de grupo incluído)
- ❌ Errado: `"I"`, `"II"` como chaves pai — corrigir com `Edit` antes de `run_stage(stage='validate')`

---

## 3. Revisar prova.md

### 3.1 Guardar o original

Antes da primeira edição, verificar se `prova_original.md` já existe. Se não existir:

```bash
cp "workspace/NOME/prova.md" "workspace/NOME/prova_original.md"
```

### 3.2 Ler — só a secção de questões

Usar `Read` para ler o `prova.md`. **Ignorar capa, instruções ao aluno e formulário matemático** (não são extraídos para JSON). Começar a leitura ativa a partir do primeiro `# GRUPO` ou do primeiro item numerado `1.`.

### 3.3 Estrutura primeiro — separar GRUPOS, PARTES e questões comparando com cotações

**Antes de qualquer correção de texto**, reconstruir mentalmente a árvore da prova e confrontá-la com `cotacoes_estrutura.json`. É a única forma de garantir que nenhum item se perdeu, se fundiu ou migrou de grupo.

**Passos obrigatórios:**

1. Ler `cotacoes_estrutura.json` — é a "tabela de verdade": lista todos os itens que **têm** de existir, com as chaves no formato `"I-A-1"`, `"I-B-4"`, `"II-2"`, `"III-1"`.
2. Percorrer o `prova.md` e montar a lista de todos os cabeçalhos encontrados:
   - `# GRUPO I` / `# GRUPO II` / `# GRUPO III`
   - `## PARTE A` / `## PARTE B` / `## PARTE C` (só no GRUPO I das provas 639)
   - Itens numerados (`1.`, `2.`, …) e subitens (`1.1.`, `1.2.`, …)
3. Confrontar as duas listas:
   - **Falta um item no `prova.md`?** → item fundido com o anterior ou com prefixo perdido pelo OCR. Localizar no PDF e restaurar o prefixo, mas **sem inventar texto**.
   - **Item a mais no `prova.md`?** → linha solta que o OCR numerou por engano, ou um exemplo/citação que ficou confundido com item. Rebaixar.
   - **Item no grupo errado?** → mover para debaixo do cabeçalho correto.
4. Confirmar que cada item está na sua própria linha e que subitens (`1.1.`) estão separados do item pai.

**Padrões de fusão/perda frequentes em Português 639:**
- Cabeçalho `## PARTE B` comido pelo parágrafo anterior → reinserir.
- Item `4.` colado ao final do texto do item `3.` (ex: `"…conclui-se a análise. 4. Explique…"`) → quebrar em duas linhas.
- Enunciado do GRUPO III interpretado como item do GRUPO II → verificar o cabeçalho de grupo.

⚠️ **Regra absoluta:** não criar, renumerar ou fundir itens por iniciativa própria. Cada alteração à árvore deve ter evidência direta no PDF ou nas cotações. Em caso de ambiguidade, reportar e parar (ver AGENTS.md §5).

### 3.3.1 Formatação de texto — quebras de linha, sobrescritos, notas de rodapé

Aplicar apenas quando o erro for **inequívoco** e a forma correta for **observável** no PDF ou noutra parte do próprio documento. Se tiveres de "deduzir" qual devia ser o número da nota ou qual palavra foi perdida, **parar e reportar** (AGENTS.md §5).

**Sempre que o stem contém texto literário, poema, prosa ou outro excerto, abrir o PDF é obrigatório** — não confiar só no markdown do MinerU. O mesmo `Read(file_path=<pdf>, pages=...)` que confirma a numeração de linhas serve para verificar:

| Aspecto | O que conferir | Como corrigir no `enunciado` |
|---|---|---|
| Números de linha | Marcadores na margem do excerto (5, 10, 15…) | Formato canónico `\n{N} <linha>` (ver fluxo abaixo) |
| Formatação | Itálico (citações, palavras estrangeiras), negrito, separação de estrofes/parágrafos, recuos | Markdown: `*itálico*`, `**negrito**`, linha em branco entre estrofes/parágrafos |
| Sobrescritos | Números marcadores de notas: `palavra²`, `cútis⁸` | Converter `palavra2`/`cútis8`/`cutisº` para Unicode sobrescrito (`²³⁴⁵⁶⁷⁸⁹`); ver §3.3.1 abaixo |
| Notas / legendas | Bloco "NOTAS": numeração bate com sobrescritos no texto, definição transcrita literalmente | Não reescrever; reportar incoerências |

Se o PDF não permite ver com certeza, marcar `[VERIFICAR]` no sítio em causa e parar — nunca deduzir.

**Quebras de linha e marcadores de numeração — VERIFICAÇÃO OBRIGATÓRIA em cada `context_stem`:**

Regex não é fiável para isto; o agente é responsável por conferir cada `context_stem` visualmente no PDF e aplicar o formato canónico. O `validate` bloqueia se o gate não for cumprido.

Fluxo obrigatório, para cada `context_stem` (`I-ctx1`, `I-ctx2`, `II-ctx1`, `III-ctx1`, …):

1. Chamar `get_context_stem_pdf_pages(workspace, id_item)` — devolve o PDF, páginas prováveis e o excerto actual de `prova.md`.
2. Abrir o PDF com `Read(file_path=<pdf>, pages="<N>-<M>")` nas páginas indicadas.
3. Contar visualmente os marcadores de linha na margem do excerto (típico: `5`, `10`, `15`…).
4. No `enunciado` em `questoes_review.json`, aplicar o **formato canónico** para cada marcador presente:
   ```
   …texto anterior termina aqui.
   5 texto que começa na linha 5 do excerto…
   10 texto que começa na linha 10…
   ```
   - Cada marcador sozinho em início de linha, seguido de **um espaço** e do conteúdo daquela linha.
   - Nunca deixar o número fundido à palavra seguinte (`5calamistrar`), inline no meio de uma frase (`… espetáculo. 15 A cara…` em linha única), nem com OCR corrompido (`|0`, `I0`, `l0`, `IO` → `10`).
   - Não juntar linhas por "fluir melhor", não quebrar linhas para "alinhar" com a numeração.
5. Decidir `tem_numeracao_linhas`:
   - `true` — o excerto original no PDF tem marcadores de linha (típico de excertos literários e textos expositivos).
   - `false` — não tem (típico do tema de dissertação em `III-ctx1` e de alguns poemas curtos).
6. Se `tem_numeracao_linhas: false`, garantir que nenhum dígito do OCR ficou colado a palavras nem solto no meio do parágrafo.
7. Marcar `linhas_verificadas: true` como último passo.

O `validate` falha alto se: `tem_numeracao_linhas` for `null`, `linhas_verificadas` for `false`, o enunciado declarar `true` mas não tiver marcadores canónicos, ou declarar `false` mas ter resíduos numéricos suspeitos.

**Sobrescritos de notas (¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹):**
- Números fundidos a palavras (`cútis8`, `palavra2`) devem virar sobrescritos (`cútis⁸`, `palavra²`), **mas só quando o número aparece explicitamente na secção NOTAS do próprio documento**.
- Se a nota está listada como `⁸ cútis: …` no bloco NOTAS, então `cútis8` → `cútis⁸` é inequívoco.
- Se o número não está listado nas NOTAS, **não transformar** — pode ser um ano, página, ou dígito do corpo do texto.
- Nunca inventar uma nota que não exista. Nunca renumerar notas.

**Bloco NOTAS:**
- Transcrever exatamente como está no PDF, incluindo abreviações e formulações estranhas.
- **Nunca** reescrever, clarificar ou expandir uma definição — mesmo que pareça incompleta ou errada (ver AGENTS.md §5, hard stops).
- Se o OCR perdeu parte de uma definição, marcar `[ILEGÍVEL]` e reportar.

**Itálicos, aspas, citações:**
- Aspas tipográficas PT: `"..."` → `«...»` quando claramente citação/fala.
- Reticências: `...` → `…` (um único caractere).
- Itálicos aparecem em títulos de obras e estrangeirismos — preservar `*palavra*` ou `_palavra_` conforme o OCR os produziu.

### 3.4 Padrões recorrentes de OCR — GRUPO I / GRUPO II

**Prefixos de item ausentes:**
- `Num dia de vento...` logo após item 3 → deve ser `4. Num dia de vento...`
- `. Considere a função` → `6. Considere a função`

**Subitens com prefixo fundido:**
- `1Colocam-se` → `2.1. Colocam-se` (verificar contra cotações)
- `3Determine` → `1.3. Determine`

**Ponto duplo:**
- `2..Considere` → `2.2. Considere`

### 3.5 Alternativas MC — VERIFICAÇÃO OBRIGATÓRIA EM TODAS

**(a) Frações truncadas** (OCR perde numerador/denominador de frações verticais):
- `(A) $\frac{1}{3}$ (B) $\frac{1}{2}$ (C) 2 (D) 5` → C e D são frações truncadas
- Inferir do contexto; confirmar no PDF com `Read(pdf, pages="N")`

**(b) Domínio matemático inválido:**
- **Probabilidade** (`P(`, `probabilidade`, `distribuição`): todas as alternativas devem estar em ]0, 1[. Qualquer inteiro ≥ 1 é fração truncada.

**(c) Sinais trocados** em frações com `\frac` — comparar as 4 alternativas entre si; se 1 é estranha ao padrão das outras 3, está errada.

**(d) Alternativas mistas** (LaTeX + texto puro) — converter texto puro para LaTeX coerente.

**(e) Expressões incompletas** — alternativas que começam com `=`, `<`, `>`, `≤`, `≥` sem membro esquerdo:
- `= -3` → `$y = -3$` (inferir variável do enunciado)
- `< 0` → `$f(x) < 0$` conforme contexto

**Alternativas com constantes de 1 char:**
- `e`, `2e`, `π`, `i` → formatar em LaTeX: `$e$`, `$2e$`, `$\pi$`, `$i$`

### 3.6 Artefactos OCR — LaTeX e texto

**Coordenadas 3D:**
- `^ h 2 1 0 , ,` → `$(2, 1, 0)$`

**Potências sem LaTeX:**
- `e3`, `e-3` → `$e^{3}$`, `$e^{-3}$`

**Frações com espaços internos:**
- `$\frac { 1 5 } { 1 6 }$` → `$\frac{15}{16}$`

**Frações coladas em alternativas:**
- `(A) 161 (B) 151 (C) 141 (D) 131` em questão de probabilidade → `(A) $\frac{1}{6}$  (B) $\frac{1}{5}$  (C) $\frac{1}{4}$  (D) $\frac{1}{3}$`

**Intervalos com delimitadores errados:**
- `\left. 0 , \frac{\pi}{4} \right.` → `$\left] 0 , \frac{\pi}{4} \right[$`
- `\left| \pi , \frac{3\pi}{2} \right|` → `$\left] \pi , \frac{3\pi}{2} \right[$`

**Artefactos textuais:**
- `]conjugado de $z$ g.` → `(conjugado de $z$).`
- `6 @ ABCDV` → `$ABCDV$`
- Símbolos soltos `@`, `~`, `^` fora de LaTeX

**Decimais portugueses:**
- `(A) 0 7,` → `(A) $0{,}7$`

### 3.7 Regra absoluta — ilegível

**Nunca deixar** `[ilegível]`, `???`, `[...]` no `prova.md` final. Sempre resolver com:
```
Read("provas fontes/.../PROVA.pdf", pages="N")
```
O PDF original é a fonte de verdade.

### 3.8 Reportar

No final da revisão, listar: correções aplicadas por tipo · itens/subitens encontrados · ambiguidades para revisão humana.

---

## 4. Revisão em lote de questoes_review.json (com categorização inline)

Após a revisão do `prova.md`, continuar automaticamente.

O `run_stage(stage='extract')` gerou `questoes_review.json` com todos os itens marcados `"reviewed": false`.

Para cada item (incluindo `context_stem`):
1. Ler `questoes_review.json` com `Read`
2. Se o item tiver `id_contexto_pai`, localizar o `context_stem` correspondente antes de rever o subitem
3. Verificar: enunciado, alternativas, tipografia PT («», …, diacríticos), imagens, notas de rodapé
4. **Confirmar `tipo_item` e formato de resposta esperado** (ver 4.0) antes de categorizar
5. Corrigir diretamente em `questoes_review.json` com `Edit` (campo a campo — não re-escrever o objeto inteiro)
6. **Preencher categorização** para **todos** os itens, **inclusivamente os `context_stem`** (ver secção 4.1)
7. Setar `"reviewed": true` no item

### 4.0 Identificar tipo de questão e formato de resposta — obrigatório antes de categorizar

O extractor atribui um `tipo_item` heurístico que frequentemente está **errado** em provas de Português. Confirmar com base no enunciado e corrigir antes de avançar.

**Mapeamento (Exame 639):**

| Sinal no enunciado | `tipo_item` correto | Campos exigidos |
|--------------------|---------------------|-----------------|
| "Na resposta a cada item, selecione a opção correta" / 4 alternativas A–D | `multiple_choice` | `alternativas` (A–D), sem `palavras_min/max` |
| "Assinale, de entre as afirmações seguintes, a(s) verdadeira(s)" / lista I, II, III, IV, V | `multi_select` | `alternativas` em numeração romana, sem letra MC |
| "Complete a tabela" / "Faça a correspondência entre…" | `complete_table` | imagem ou tabela markdown no enunciado |
| "Explicite…", "Justifique…", "Explique…", "Relacione…" sem limite de palavras de redação | `open_response` | sem `palavras_min/max` |
| "Redija um texto…" / "Numa exposição de 200 a 350 palavras…" | `essay` | `palavras_min`, `palavras_max` preenchidos |
| Excerto, poema, texto expositivo, tema da dissertação | `context_stem` | sem pontuação, com `id_item` `I-ctx1` etc. |

**Regras:**
- Se o enunciado pede resposta escrita mas **não dá limite de palavras**, é `open_response` (não `essay`).
- Se o enunciado usa numeração romana (I, II, III…) em afirmações para marcar V/F, é `multi_select` — **não** `multiple_choice`, mesmo que o extractor tenha posto letras A–D.
- Se corrigires `tipo_item` aqui, anotar mentalmente para confirmar depois no critério correspondente (secção 6b.1).

Só avançar quando **todos** os itens (incluindo os `context_stem`) tiverem `"reviewed": true` e estiverem categorizados.

> ⚠️ `run_stage(stage='validate')` bloqueia se existirem itens com `"reviewed": false`.
> ⚠️ `run_stage(stage='merge')` bloqueia se `tema`, `subtema`, `descricao_breve` ou `tags` faltarem em qualquer item (inclusive `context_stem`).

### 4.1 Categorização específica de Português — seja granular, evite genérico

**Regra fundamental:** não escrever apenas `tema: "Narrativa"` / `subtema: "Coração, Cabeça e Estômago"`. Essa categorização é demasiado genérica — perde-se o conteúdo específico que o item avalia. A categorização deve permitir a um professor encontrar rapidamente o item pelo conteúdo programático e pelas competências testadas.

**Tema (domínio curricular + género/subdomínio):**
Use a forma `"<Domínio> — <Género/Subdomínio>"`. Exemplos válidos:
- `"Educação Literária — Narrativa do século XIX"`
- `"Educação Literária — Poesia de Fernando Pessoa"`
- `"Educação Literária — Sermão do Padre António Vieira"`
- `"Educação Literária — Os Lusíadas"`
- `"Educação Literária — Memorial do Convento"`
- `"Leitura — Texto expositivo"`
- `"Leitura — Texto argumentativo"`
- `"Gramática — Sintaxe"`
- `"Gramática — Semântica lexical"`
- `"Gramática — Coesão textual"`
- `"Escrita — Apreciação crítica"`
- `"Escrita — Exposição sobre um tema"`
- `"Oralidade — Compreensão"`

**Subtema (obra + unidade específica ou, para gramática/escrita, o conteúdo preciso):**
Obrigatório identificar a obra, o autor e o recorte concreto. Exemplos:
- `"Camilo Castelo Branco, «Coração, Cabeça e Estômago» — caracterização do protagonista"`
- `"Fernando Pessoa / Álvaro de Campos — heteronímia e fingimento poético"`
- `"Padre António Vieira, «Sermão de Santo António aos Peixes» — alegoria e crítica social"`
- `"Luís de Camões, «Os Lusíadas» — episódio da Despedida em Belém (Canto IV)"`
- `"José Saramago, «Memorial do Convento» — relação Blimunda/Baltasar"`
- `"Funções sintáticas — complemento oblíquo vs. modificador"`
- `"Processos de coesão — coesão referencial (anáfora e catáfora)"`
- `"Valor aspectual — aspeto imperfetivo/perfetivo"`

**descricao_breve (frase curta que descreve a tarefa, não o tema):**
Deve começar por verbo de tarefa (Explicar, Justificar, Identificar, Relacionar, Associar, Selecionar, Completar, Redigir…). Exemplos:
- `"Explicitar a imagem ficcional construída pelo protagonista e a sua intenção."`
- `"Identificar dois aspetos que evidenciam a caricatura do herói romântico."`
- `"Explicar o papel da máscara na dualidade do sujeito poético."`
- `"Associar afirmações sobre o poema à sua validade (verdadeiras/falsas)."`
- `"Identificar a função sintática de um segmento sublinhado."`
- `"Redigir uma exposição sobre a importância da memória na construção da identidade (200–350 palavras)."`

**tags (5–8 strings específicas — conteúdos, recursos, conceitos):**
Combinar: nome da obra/autor abreviado + competência + recurso expressivo/conteúdo linguístico concreto. Evitar tags vagas como `"interpretação"`, `"análise"`, `"português"`.

Exemplos bem granulados:
- Item I-1 sobre farsa em Coração, Cabeça e Estômago:
  `["camilo castelo branco", "coração cabeça e estômago", "herói romântico", "caricatura", "ironia", "construção do protagonista", "farsa", "simulação"]`
- Item I-4 sobre a máscara em Álvaro de Campos:
  `["álvaro de campos", "modernismo", "heteronímia", "dualidade do sujeito poético", "máscara", "fingimento", "identidade", "símbolo"]`
- Item I-6 multi_select sobre o poema:
  `["álvaro de campos", "análise textual", "verso livre", "anáfora", "reticências", "ritmo", "verdadeiro/falso"]`
- Item de gramática sobre função sintática:
  `["gramática", "sintaxe", "função sintática", "complemento oblíquo", "modificador", "frase complexa"]`
- Item III (essay) de apreciação crítica:
  `["escrita", "apreciação crítica", "argumentação", "200-350 palavras", "tema: memória", "coesão textual"]`

### 4.2 Categorização dos `context_stem`

Os `context_stem` (id_item `I-ctx1`, `I-ctx2`, `II-ctx1`, `III-ctx1`, etc.) representam o excerto literário, o texto expositivo, o poema ou o tema da dissertação. **Também** devem ser categorizados:

- `tema`: mesmo domínio que as questões filhas (ex: `"Educação Literária — Narrativa do século XIX"`, `"Leitura — Texto expositivo"`, `"Escrita — Apreciação crítica"`).
- `subtema`: identificar obra + autor + recorte (para excertos literários) ou tipologia + tema (para textos expositivos e tema de dissertação).
- `descricao_breve`: uma frase resumindo o conteúdo do texto-âncora (ex: `"Excerto sobre a transformação física do protagonista em herói romântico."`, `"Texto expositivo sobre o papel das bibliotecas públicas."`, `"Tema de dissertação: importância da memória coletiva."`).
- `tags`: autor, obra, género, recursos dominantes, tema do texto.

Exemplo para o excerto de Coração, Cabeça e Estômago (I-A-ctx):
```json
"tema": "Educação Literária — Narrativa do século XIX",
"subtema": "Camilo Castelo Branco, «Coração, Cabeça e Estômago» — caricatura do herói romântico",
"descricao_breve": "Excerto em que o narrador descreve a construção da sua imagem de herói romântico através de alterações físicas.",
"tags": ["camilo castelo branco", "século XIX", "novela", "romantismo", "caricatura", "narrador autodiegético", "humor"]
```

Exemplo para o poema de Álvaro de Campos (I-B-ctx):
```json
"tema": "Educação Literária — Poesia de Fernando Pessoa",
"subtema": "Álvaro de Campos — máscara e dualidade do sujeito poético",
"descricao_breve": "Poema de Álvaro de Campos sobre o ato de retirar e voltar a pôr a máscara como metáfora da identidade.",
"tags": ["fernando pessoa", "álvaro de campos", "modernismo", "heteronímia", "máscara", "dualidade", "fingimento", "verso livre"]
```

---

## 5. Lint e validação

```
run_stage(workspace="NOME", stage="validate")
```

Internamente corre micro-lint e depois a validação heurística. Se houver erros, avaliar se são corrigíveis com `Edit` em `questoes_raw.json` antes de reportar ao utilizador.

---

## 6. Critérios CC-VD (se aplicável)

### 6a. MinerU no CC-VD (fora do sandbox)

```bash
MINERU="/Users/adrianoushinohama/dev/Exames Nacionais/Provas de matemática/.venv-mineru/bin/mineru"
"$MINERU" -b pipeline \
  -p "provas fonte/PROVA-CC-VD.pdf" \
  -o "workspace/NOME-CC-VD"
cp <caminho_encontrado> workspace/NOME-CC-VD/prova.md
```

Depois (1ª chamada — extrai critérios):
```
run_stage(workspace="NOME", stage="cc", workspace_cc="NOME-CC-VD")
```

### 6b. Revisão de criterios_raw.json

`criterios_raw.json` tem itens com `"reviewed": false`. Para cada item:
1. Verificar: `solucao`, `criterios_parciais`, `resposta_correta` (MC), `resolucoes_alternativas`
2. Para MC com `resposta_correta` vazia: **ler `workspace/NOME-CC-VD_net/prova.md`** (output do MinerU) e procurar a tabela "CHAVE DE RESPOSTA" do GRUPO II (ou equivalente). O MinerU transcreve a tabela como markdown — copiar a letra de lá. **Não ler o PDF**: o markdown é a fonte de verdade.
3. Para itens de resposta aberta com 0 etapas: extrair do `bloco_ocr` ou do `prova.md` do workspace CC. **Não ler o PDF** salvo último recurso.
4. Corrigir diretamente em `criterios_raw.json`
5. Setar `"reviewed": true`

**Não categorizar** no fluxo CC-VD.

#### 6b.0 O que NÃO copiar / o que copiar via PyMuPDF

**Ignorar sempre** (genérico, igual em todos os anos):
- **Critérios Gerais de Classificação** — preâmbulo nas primeiras ~3 páginas. O extractor já corta na âncora `# CRITÉRIOS ESPECÍFICOS DE CLASSIFICAÇÃO`.
- **Tabela CL ("Aspectos de correção linguística")** — grelha 3 pontos tipo A/B. Modelada via `parametros_classificacao`.

**Capturar apenas o descritor do nível máximo via PyMuPDF**:
- **Tabela C-ED ("Aspectos de conteúdo e de estruturação do discurso")** — descritores são específicos de cada questão. Capturar **só o Nível 5** (ou o de pontuação máxima — coincide com o valor da bullet "C-ED ............ N pontos"). Os níveis 4–1 são derivados — não copiar.

O MinerU pode degradar a estrutura tabular. Ler directamente do PDF com `fitz`:

```python
import fitz
doc = fitz.open("provas fonte/.../EX-Port639-...-CC.pdf")
page = doc[N - 1]   # N = página da tabela C-ED da questão (1-indexed → 0-indexed)
text = page.get_text()
# Localizar o bloco entre "Níveis" e a linha "4" (ou "OU") — é o Nível 5
```

Colocar o texto num único `criterios_parciais` da questão essay com `pontos` = pontuação máxima da bullet (ex.: 10).

**Regra geral:** se um descritor é igual em provas de anos diferentes (CL, níveis 4–1 da C-ED), é genérico → não copiar. Específico = só o Nível 5 da C-ED.

#### 6b.0.1 Espelhar `solucao` em `criterios_parciais`

Para `open_response` e `essay`: depois de preencher `solucao` com a resolução completa, copiar o mesmo texto para `criterios_parciais` (descrição do nível máximo). O preview e o Supabase apresentam-nos por caminhos distintos; deixar `criterios_parciais` só com o descritor C-ED esconde a resposta esperada do classificador humano.

```json
"solucao": "<resolução completa>",
"criterios_parciais": [
  {"nivel": "5", "pontos": 10, "descricao": "<descritor C-ED N5> + <resolução completa>"}
]
```

Não aplicar a MC (`solucao` trivial = letra correcta).

#### 6b.1 Match critério ↔ questão — obrigatório

Cada critério em `criterios_raw.json` tem de ter uma questão correspondente em `../<workspace_principal>/questoes_review.json` com o **mesmo `id_item`**. Antes de marcar `"reviewed": true`:

1. **Cobertura:** listar todos os `id_item` de `questoes_review.json` (excluindo `context_stem`) e confirmar que cada um tem um critério correspondente. Listar todos os `id_item` de `criterios_raw.json` e confirmar que cada um tem uma questão. Qualquer questão sem critério ou critério sem questão = bug a reportar.
2. **Coerência de tipo:** ler o `tipo_item` da questão e confirmar que o critério usa o campo de resposta adequado (tabela abaixo).
3. **Coerência de pontuação:** confirmar que a pontuação total do critério bate com o valor em `cotacoes_estrutura.json`.

Para cada critério, ler também o `tipo_item` da questão correspondente em `../<workspace_principal>/questoes_review.json`. O extractor já bloqueia falsas classificações como `multiple_choice` para tipos não-MC, mas o agente deve **confirmar a coerência** e preencher a resposta no campo correcto:

| `tipo_item` da questão | Campo de resposta | O que fazer |
|------------------------|-------------------|-------------|
| `multiple_choice` | `resposta_correta: "B"` | Confirmar letra A–D contra o PDF CC-VD. |
| `multi_select` | `respostas_corretas: ["I","III","IV"]` | Ler `Read("provas fontes/<CC>.pdf", pages=N)` na página do item. Preencher com os algarismos romanos das afirmações verdadeiras. **Apagar** qualquer `resposta_correta` letra MC herdada (contaminação OCR). |
| `complete_table` | `respostas_corretas: ["a→3","b→1","c→2"]` | Ler PDF; preencher pares chave→opção. **Apagar** `resposta_correta` se presente. |
| `essay` | `parametros_classificacao` (no JSON da questão) | Confirmar Parâmetros A/B/C com níveis N5–N1. O critério não tem campo de resposta única. |
| `open_response` | `criterios_parciais` + `solucao` | Verificar etapas e pontuação. |

**Regra de ouro:** se o `tipo` no critério não bate com o `tipo_item` da questão, corrigir o `tipo` do critério primeiro e só depois extrair a resposta do PDF — nunca aceitar a letra MC herdada do extractor automático.

> ⚠️ `cc_validate` rejeita o critério se: (a) `multi_select`/`complete_table` com `resposta_correta` MC presente, (b) `multi_select`/`complete_table` com `respostas_corretas` vazio, (c) `multi_select` com menos de 2 respostas.

#### 6b.2 Critérios com duas versões de prova (Versão 1 / Versão 2) — manter apenas Versão 1

Algumas provas (tipicamente itens `multi_select` e `complete_table`) apresentam **duas versões** no CC-VD, com gabaritos distintos. Exemplo:

```
6. ........................................................
   Versão 1 – a) → 2; b) → 2
   Versão 2 – a) → 1; b) → 3
```

```
3. ........................................................
   Versão 1 – I, II e IV
   Versão 2 – II, III e V
```

**Regra absoluta:** considerar **apenas a Versão 1** e **apagar a Versão 2** dos critérios. O pipeline publica uma única versão da prova — a segunda versão geraria respostas duplicadas e inconsistentes no Supabase.

Fluxo ao encontrar uma entrada com duas versões em `criterios_raw.json`:
1. Identificar o par Versão 1 / Versão 2 no `bloco_ocr` ou `solucao` do item.
2. Preencher `respostas_corretas` (ou `resposta_correta`, conforme o tipo) **só com os valores da Versão 1**.
3. Remover da `solucao` e de qualquer campo auxiliar o texto referente à Versão 2 (linha inteira: `"Versão 2 – …"`).
4. Se existir um marcador residual `"Versão 1 –"` no início, limpar o prefixo para deixar apenas o conteúdo canónico da resposta.
5. Só depois marcar `"reviewed": true`.

Nunca fundir as duas versões, nem preencher arrays com a união dos valores — isto corromperia o gabarito.

### 6c. Validar e fundir

```
# 2ª chamada — valida após revisão
run_stage(workspace="NOME", stage="cc", workspace_cc="NOME-CC-VD")

# Merge com questões aprovadas + abre preview
run_stage(workspace="NOME", stage="merge", workspace_cc="NOME-CC-VD")
```

---

## 7. Revisão humana e upload

Após `run_stage(stage='merge')`, o preview abre automaticamente. O utilizador deve rever e clicar "✅ Aprovar para Upload".

Para verificar o estado do preview / reabrir:
```
run_review(workspace="NOME")
```

Só depois:
```
run_stage(workspace="NOME", stage="upload")
```

Se o utilizador pedir correções pontuais após a revisão:
```
run_fix_question(workspace="NOME", id_item="II-3.2", field="enunciado", value="...")
```
> ⚠️ `run_fix_question` reseta a aprovação — nova revisão humana é necessária.

---

## 8. Problemas comuns

| Sintoma | Solução |
|---------|---------|
| Tools `mcp__exames-pipeline__*` não aparecem | Reiniciar Claude Code |
| `run_stage(stage='extract')` retorna erro de módulo | Verificar PYTHONPATH no `.mcp.json` |
| `run_stage(stage='validate')` bloqueia com `reviewed: false` | Rever todos os itens em `questoes_raw.json`, setar `reviewed: true` |
| MinerU OOM (GPU) | Usar flag `-b pipeline` no comando manual |
| Workspace não encontrado | Verificar que `PIPELINE_ROOT/workspace/NOME` existe |
| `run_stage(stage='upload')` bloqueado | Utilizador ainda não clicou "✅ Aprovar" no preview |
| `No module named 'mcp'` | `/opt/homebrew/bin/python3.11 -m pip install "mcp[cli]"` |
| Estado inesperado / dúvida | `workspace_status(workspace="NOME")` — mostra estado + próxima acção |
