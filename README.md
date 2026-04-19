# Exames Nacionais — Pipeline de Questões

Pipeline modular para extrair, validar, categorizar e publicar questões de provas de exames nacionais (Portugal) a partir de PDFs, gerando JSON estruturado no Supabase/PostgreSQL.

**Objetivo final:** pool de milhares de questões de múltiplas disciplinas e anos, pesquisáveis por tópico via heurística ou IA semântica, servidas num site como quiz interativo ou PDF imprimível.

**Stack:** MinerU (OCR) · Agent LLM (agente) · Supabase + pgvector (base de dados)  
**Repositório:** `Blackcoffee111/extrator-de-questoes`

> **Princípio de design:** nenhum módulo faz chamadas a APIs externas de LLM.
> Todo o trabalho de inteligência é feito pelo agente Claude Code diretamente via Read + Edit.

---

## Instalação

### Requisitos

- macOS / Linux
- Python 3.11 (pipeline) + Python 3.12 (MinerU, venv separado)
- Conta Supabase com extensões `uuid-ossp`, `vector` e `unaccent` ativas

### 1. Clonar e instalar dependências

```bash
git clone https://github.com/Blackcoffee111/extrator-de-questoes.git
cd extrator-de-questoes
/opt/homebrew/bin/python3.11 -m pip install "mcp[cli]" pymupdf Pillow supabase
```

### 2. Instalar MinerU num venv isolado

```bash
python3.12 -m venv .venv-mineru
.venv-mineru/bin/pip install -U "mineru[all]"
```

### 3. Configurar o `.env`

```bash
cp .env.example .env
# Editar .env com as credenciais Supabase
```

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=eyJ...    # service_role key
MINERU_VENV=./.venv-mineru
MINERU_MODE=math_heavy
```

### 4. Criar o schema no Supabase

No SQL Editor do Supabase, ativar as extensões (`vector`, `unaccent`) e executar em ordem:

```
migrations/v2/001_schema_v2.sql
migrations/v2/002_patch_grupo_constraint.sql
migrations/v2/003_rls.sql
```

### 5. Configurar o servidor MCP

O `.mcp.json` já está no repositório com os caminhos corretos para este ambiente.
Para outros ambientes, ver [`docs/mcp_server.md`](docs/mcp_server.md).

Reiniciar o Claude Code após qualquer alteração ao `.mcp.json`.

---

## Uso rápido

Com o MCP configurado, basta dizer ao agente:

> *"Processa o PDF da prova de 2025"*

O agente segue o fluxo completo: OCR → revisão → validação → critérios → upload.
Invocar `/exames` para ver o checklist detalhado de cada fase.

---

## Banco de dados (schema v2)

| Tabela | Descrição |
|--------|-----------|
| `materias` | Disciplinas: "Matemática A", "Física A", etc. |
| `fontes` | Exames: tipo, ano, fase, instituição |
| `topicos` | Taxonomia hierárquica: tema → subtema |
| `contextos` | Enunciados partilhados por grupos de sub-questões |
| `questoes` | Questões com embedding pgvector + FTS português |

Ver [`docs/database.md`](docs/database.md) para documentação completa do schema.

---

## Roadmap

- [ ] Popular embeddings pgvector para busca semântica
- [ ] Adicionar outras disciplinas (Física A, Química A, História A)
- [ ] Site público: busca por tópico + quiz interativo + PDF imprimível
