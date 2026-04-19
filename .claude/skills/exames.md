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
PIPELINE_ROOT="/Users/adrianoushinohama/Desktop/Exames Nacionais"

/opt/homebrew/bin/python3.11 -c "import mcp, pymupdf, supabase; print('✅ deps ok')" 2>&1
$PIPELINE_ROOT/.venv-mineru/bin/mineru --version 2>&1
ls $PIPELINE_ROOT/.env && echo "✅ .env presente" || echo "❌ .env ausente"
```

Se as tools `mcp__exames-pipeline__*` estiverem disponíveis, o servidor MCP está ativo.
Se não estiverem, instruir o utilizador a reiniciar o Claude Code.

Usar `workspace_status(workspace)` sempre que em dúvida sobre o estado de um workspace.

---

## 2. Executar MinerU (fora do sandbox)

> ⚠️ MinerU falha em ambientes sandbox (multiprocessing bloqueado). Pedir ao utilizador para correr no Terminal:

```bash
cd "/Users/adrianoushinohama/Desktop/Exames Nacionais"
.venv-mineru/bin/mineru -b pipeline -p "provas fontes/PROVA.pdf" -o workspace/NOME
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

### 3.3 Verificar separação de itens e subitens

- Cada item numerado (`1.`, `2.`, ...) deve estar na sua própria linha
- Subitens (`1.1.`, `1.2.`, ...) separados do item pai
- Verificar contra a tabela de cotações no fim do documento

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

## 4. Revisão em lote de questoes_raw.json (com categorização inline)

Após a revisão do `prova.md`, continuar automaticamente.

O `run_stage(stage='extract')` gerou `questoes_raw.json` com todos os itens marcados `"reviewed": false`.

Para cada item:
1. Ler `questoes_raw.json` com `Read`
2. Se o item tiver `contexto_pai_ref`, ler o item pai antes de rever o subitem
3. Verificar: enunciado, alternativas, tipo, LaTeX, imagens referenciadas
4. Corrigir diretamente em `questoes_raw.json` com `Edit` (campo a campo — não re-escrever o objeto inteiro)
5. **Preencher categorização** para cada item (exceto `context_stem`) enquanto o conteúdo está fresco:
   - `tema`: tema principal do currículo de Matemática A (ex: `"Funções"`, `"Geometria"`, `"Probabilidades"`, `"Trigonometria"`, `"Números complexos"`, `"Sucessões"`, `"Combinatória"`)
   - `subtema`: subtema específico (ex: `"Funções trigonométricas"`, `"Geometria no espaço"`, `"Distribuição binomial"`)
   - `descricao_breve`: frase curta (ex: `"Cálculo de probabilidade condicional"`)
   - `tags`: lista de 3–5 strings (ex: `["probabilidade", "independência", "P(A∩B)"]`)
6. Setar `"reviewed": true` no item

Só avançar quando **todos** os itens tiverem `"reviewed": true`.

> ⚠️ `run_stage(stage='validate')` bloqueia se existirem itens com `"reviewed": false`.

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
.venv-mineru/bin/mineru -b pipeline \
  -p "provas fontes/PROVA-CC-VD.pdf" \
  -o workspace/NOME-CC-VD
cp <caminho_encontrado> workspace/NOME-CC-VD/prova.md
```

Depois (1ª chamada — extrai critérios):
```
run_stage(workspace="NOME", stage="cc", workspace_cc="NOME-CC-VD")
```

### 6b. Revisão de criterios_raw.json

`criterios_raw.json` tem itens com `"reviewed": false`. Para cada item:
1. Verificar: `solucao`, `criterios_parciais`, `resposta_correta` (MC), `resolucoes_alternativas`
2. Para MC com `resposta_correta` vazia: ler imagem do gabarito no PDF com `Read` e preencher
3. Para itens de resposta aberta com 0 etapas: extrair do `bloco_ocr` ou PDF com `Edit`
4. Corrigir diretamente em `criterios_raw.json`
5. Setar `"reviewed": true`

**Não categorizar** no fluxo CC-VD.

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
