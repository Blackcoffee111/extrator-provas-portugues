# MCP Server — Exames Nacionais Pipeline

Servidor MCP (Model Context Protocol) que expõe o pipeline de extração de questões como ferramentas chamáveis por qualquer IA compatível com MCP.

**Transporte:** stdio (processo iniciado pela IA, sem servidor permanente)
**Protocolo:** MCP 2024-11-05
**Linguagem:** Python 3.11 (pipeline) + Python 3.12 (MinerU, venv separado)

---

## Estrutura de diretórios (macOS — este ambiente)

```
/Users/adrianoushinohama/Desktop/Exames Nacionais/   ← PIPELINE_ROOT
├── .env                    ← credenciais (único, na raiz)
├── .mcp.json               ← config do servidor MCP
├── .venv-mineru/           ← Python 3.12 com MinerU instalado
├── src/exames_pipeline/    ← código do pipeline (PYTHONPATH aponta aqui/../)
├── workspace/              ← workspaces por prova
└── provas fontes/          ← PDFs originais
```

---

## Pré-requisitos

```bash
# Python 3.11 (pipeline)
/opt/homebrew/bin/python3.11 --version   # >= 3.11

# Dependências do pipeline (instalar no Python 3.11)
/opt/homebrew/bin/python3.11 -m pip install \
  "mcp[cli]" pymupdf Pillow requests \
  google-generativeai anthropic supabase

# Python 3.12 + MinerU (venv isolado)
python3.12 -m venv .venv-mineru
.venv-mineru/bin/pip install -U "mineru[all]"
```

### Ficheiro `.env` (na raiz do projeto)

```env
SUPABASE_URL=https://<projeto>.supabase.co
SUPABASE_KEY=<service_role_key>

# MinerU (já configurado no .mcp.json)
MINERU_VENV=./.venv-mineru
MINERU_MODE=math_heavy
```

As credenciais de provider LLM já não são necessárias para o fluxo principal da prova.
Só são úteis para módulos opcionais como `run_doc_audit`, ou para fluxos CC que ainda usem provider configurado.

---

## Configuração por cliente

### Claude Code (configuração deste ambiente)

O `.mcp.json` já está na raiz do projecto com os caminhos corretos:

```json
{
  "mcpServers": {
    "exames-pipeline": {
      "command": "/opt/homebrew/bin/python3.11",
      "args": ["-m", "exames_pipeline.mcp_server"],
      "env": {
        "PYTHONPATH": "/Users/adrianoushinohama/Desktop/Exames Nacionais/src",
        "PIPELINE_ROOT": "/Users/adrianoushinohama/Desktop/Exames Nacionais",
        "MINERU_PYTHON": "/Users/adrianoushinohama/Desktop/Exames Nacionais/.venv-mineru/bin/python"
      }
    }
  }
}
```

Reiniciar o Claude Code após qualquer alteração ao `.mcp.json`.

---

### Claude Code (outro ambiente — template genérico)

```json
{
  "mcpServers": {
    "exames-pipeline": {
      "command": "python3.11",
      "args": ["-m", "exames_pipeline.mcp_server"],
      "env": {
        "PYTHONPATH": "/caminho/para/repo/src",
        "PIPELINE_ROOT": "/caminho/para/repo",
        "MINERU_PYTHON": "/caminho/para/repo/.venv-mineru/bin/python"
      }
    }
  }
}
```

Variáveis de ambiente do servidor:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `PYTHONPATH` | ✅ | Deve apontar para `repo/src` |
| `PIPELINE_ROOT` | ✅ | Raiz do repositório (onde está o `.env` e `workspace/`) |
| `MINERU_PYTHON` | ✅ | Python do venv com MinerU instalado |
| `PIPELINE_PYTHON` | ❌ | Python do pipeline (default: `/opt/homebrew/bin/python3.11`) |

---

### Claude Desktop (macOS)

Editar `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "exames-pipeline": {
      "command": "/opt/homebrew/bin/python3.11",
      "args": ["-m", "exames_pipeline.mcp_server"],
      "env": {
        "PYTHONPATH": "/Users/adrianoushinohama/Desktop/Exames Nacionais/src",
        "PIPELINE_ROOT": "/Users/adrianoushinohama/Desktop/Exames Nacionais",
        "MINERU_PYTHON": "/Users/adrianoushinohama/Desktop/Exames Nacionais/.venv-mineru/bin/python"
      }
    }
  }
}
```

Reiniciar o Claude Desktop. O ícone 🔌 na barra inferior confirma que o servidor está ativo.

---

### Cursor / Windsurf

Adicionar nas configurações MCP do IDE com os mesmos parâmetros acima.

---

### Teste manual (linha de comando)

```bash
cd "/Users/adrianoushinohama/Desktop/Exames Nacionais"

PYTHONPATH=src PIPELINE_ROOT=$(pwd) MINERU_PYTHON=.venv-mineru/bin/python \
  /opt/homebrew/bin/python3.11 -m exames_pipeline.mcp_server
```

Para inspecionar as tools interativamente:
```bash
PYTHONPATH=src PIPELINE_ROOT=$(pwd) \
  mcp dev -m exames_pipeline.mcp_server
# Abre inspector em http://localhost:5173
```

---

## Ferramentas disponíveis (12 tools)

### `list_workspaces`
Lista todos os workspaces e o estado de cada etapa.

**Parâmetros:** nenhum

**Exemplo:**
```
Workspace                       MD   Raw  Apr  Fin  CC   UP
------------------------------------------------------------
EX-MatA635-F1-2024_net          ✅    21   20   20   ❌   ✅
EX-MatA635-F1-2023              ✅    22   22    -   ❌   ❌
```

---

### `workspace_status`
Estado detalhado de um workspace.

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `workspace` | string | Ex: `"EX-MatA635-F1-2024_net"` |

---

### `run_mineru` ⭐ (recomendado para MinerU)
Corre o MinerU directamente e copia `prova.md` + `images/` para a raiz do workspace.

> ⚠️ **Requer execução fora do sandbox do Claude Code.** O MinerU usa multiprocessing e é bloqueado pelo sandbox. Se a tool falhar com timeout ou erro de permissão, correr manualmente no Terminal (ver abaixo).

| Parâmetro | Tipo | Default | Descrição |
|---|---|---|---|
| `pdf_path` | string | — | Caminho absoluto para o PDF |
| `workspace` | string | — | Nome do workspace |
| `backend` | string | `"pipeline"` | Sempre `"pipeline"` (CPU puro — único modo suportado neste projecto) |

**Uso:**

```
run_mineru(pdf_path="...", workspace="...")
```

> ℹ️ **M1 Air 8 GB:** GPU mode (`-m auto`) foi testado e descartado — o VLM MLX consome toda a RAM unificada e causa falhas. O projecto usa exclusivamente `-b pipeline` (CPU). O modelo VLM foi removido do disco.

---

### `run_extract`
Extrai questões de um PDF (módulos 1+2): MinerU → Markdown → JSON draft + chunks de revisão.

> ⚠️ **MinerU requer execução fora do sandbox.** Preferir `run_mineru`. Se for necessário correr manualmente no Terminal:
> ```bash
> cd "/Users/adrianoushinohama/Desktop/Exames Nacionais"
> .venv-mineru/bin/mineru -p "provas fontes/PROVA.pdf" -o workspace/NOME -b pipeline
> # Copiar prova.md e imagens para a raiz do workspace:
> cp workspace/NOME/NOME/auto/PROVA.md workspace/NOME/prova.md
> cp -r workspace/NOME/NOME/auto/images workspace/NOME/images
> # Depois correr o parser:
> PYTHONPATH=src python3.11 -m exames_pipeline.cli structure workspace/NOME/prova.md
> ```
> Depois do `run_extract`, o agente deve rever `questoes_review_chunks.json` e atualizar `questoes_raw.json` antes de correr `run_micro_lint` e `run_validate`.

| Parâmetro | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `pdf_path` | string | ✅ | Caminho absoluto para o PDF |
| `workspace` | string | ❌ | Nome do workspace (inferido do PDF se omitido) |

---

### `run_validate`
Validação heurística endurecida (módulo 3). Gera `questoes_aprovadas.json` + `questoes_com_erro.json`.

Além dos checks estruturais, agora também sinaliza:
- LaTeX com delimitadores `$` desequilibrados
- alternativas duplicadas ou com marcador trocado
- alternativas ainda fundidas no enunciado
- item ainda marcado como `review-pending`

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `workspace` | string | Nome do workspace |

### `run_micro_lint`
Aplica correções determinísticas leves e gera `questoes_micro_lint.json`.

Executar sempre depois da revisão em lote do agente e antes do `run_validate`.

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `workspace` | string | Nome do workspace |

---

### `run_doc_audit`
Auditoria opcional do documento completo para comparar `prova.md` com `questoes_raw.json` (módulo 2.5).

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `workspace` | string | Nome do workspace |

---

### `run_cc_extract`
Extrai critérios do PDF CC-VD (módulo 6a). Requer `prova.md` já no workspace CC.

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `workspace_cc` | string | Ex: `"EX-MatA635-F1-2023-CC-VD"` |

---

### `run_cc_validate`
Valida critérios contra `cotacoes_estrutura.json` (módulo 6b).

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `workspace_cc` | string | Nome do workspace CC |

---

### `run_cc_merge`
Merge dos critérios com `questoes_aprovadas.json` → `questoes_final.json` (módulo 6c).

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `workspace` | string | Workspace da prova |
| `workspace_cc` | string | Workspace CC-VD |

---

### `run_upload`
Envia `questoes_final.json` para o Supabase (módulo 7).

| Parâmetro | Tipo | Default | Descrição |
|---|---|---|---|
| `workspace` | string | — | Nome do workspace |
| `dry_run` | boolean | `false` | Simula sem enviar |

---

### `run_pipeline`
Corre a sequência após `prova.md` e `questoes_raw.json` existirem e após a revisão em lote do agente já ter sido aplicada ao JSON.

**Sequência:** micro-lint → validate → cc_merge (se cc disponível) → upload

| Parâmetro | Tipo | Default | Descrição |
|---|---|---|---|
| `workspace` | string | — | Workspace da prova |
| `workspace_cc` | string | `null` | Workspace CC-VD (opcional) |
| `dry_run_upload` | boolean | `false` | Simular upload |

---

## Exemplos de uso com IA

```
"Mostra o estado de todos os workspaces"
→ list_workspaces()

"Processa o workspace EX-MatA635-F1-2023 com os critérios de EX-MatA635-F1-2023-CC-VD"
→ run_pipeline(workspace="EX-MatA635-F1-2023", workspace_cc="EX-MatA635-F1-2023-CC-VD")

"Faz dry-run do upload do workspace 2023"
→ run_upload(workspace="EX-MatA635-F1-2023", dry_run=True)

```

---

## Estrutura de workspaces

```
workspace/
  EX-MatA635-F1-2023/              ← workspace da prova
    prova.md                        ← gerado por MinerU
    questoes_raw.json               ← gerado por structure
    questoes_aprovadas.json         ← gerado por validate
    questoes_com_erro.json          ← gerado por validate
    questoes_final.json             ← gerado por cc-merge
    cotacoes_estrutura.json         ← gerado por extract-cotacoes-structure
    .upload_done                    ← flag criada por upload
    images/                         ← imagens extraídas pelo MinerU
  EX-MatA635-F1-2023-CC-VD/        ← workspace dos critérios
    prova.md                        ← gerado por MinerU
    criterios_raw.json              ← gerado por cc-extract
    criterios_aprovados.json        ← gerado por cc-validate
    criterios_com_erro.json         ← gerado por cc-validate
```

---

## Resolução de problemas

### `No module named 'exames_pipeline'`
O `PYTHONPATH` está errado — deve apontar para `repo/src/`, não para a raiz.

### `GEMINI_API_KEY não configurada`
O `.env` não está a ser encontrado. Verificar que `PIPELINE_ROOT` aponta para a pasta que contém o `.env`.

### `No module named 'mcp'`
Instalar: `/opt/homebrew/bin/python3.11 -m pip install "mcp[cli]"`

### MinerU falha com `Insufficient Memory`
Usar backend CPU: `.venv-mineru/bin/mineru -p PDF -o DEST -b pipeline`

### Timeout nas tools longas
Padrão: 300s. Editar em `mcp_server.py`:
```python
result = subprocess.run(..., timeout=600)
```
