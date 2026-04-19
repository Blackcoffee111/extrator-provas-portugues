# Base de Dados — Exames Nacionais Pipeline

**Schema:** v2
**Motor:** PostgreSQL 15+ (Supabase)
**Migração:** `migrations/v2/001_schema_v2.sql`

---

## Visão Geral

O objectivo do projecto é manter um **pool de milhares de questões** de exames de múltiplas matérias e anos, pesquisável por tópico via heurística ou IA semântica, e exportável como quiz HTML interactivo ou PDF imprimível.

O schema foi desenhado com três prioridades:

1. **Searchability** — filtros rápidos por matéria/tema/subtema/tags + busca full-text em português + busca semântica por vector embedding
2. **Escalabilidade** — tabelas normalizadas para matérias, fontes e tópicos; sem duplicação de dados
3. **Flexibilidade** — suporte a questões de múltipla escolha, resposta aberta, compostas; contextos partilhados entre sub-questões

---

## Diagrama de Entidades

```
materias (1)──<(N) fontes (1)──<(N) questoes
                                     │
topicos (auto-ref: pai_id)──────────>│ (topico_id)
                                     │
contextos (1)──────────────────<(N) questoes
   └── pertence a uma fonte
```

---

## Tabelas

### `materias`

Uma linha por disciplina. Serve como âncora para `fontes` e `topicos`.

| Coluna      | Tipo    | Notas |
|-------------|---------|-------|
| `id`        | uuid PK | auto |
| `codigo`    | text    | slug único: `"mat-a"`, `"fisica-a"`, `"enem-matematica"` |
| `nome`      | text    | legível único: `"Matemática A"`, `"Física"` |
| `nivel`     | text    | `'basico'` \| `'secundario'` \| `'universitario'` \| `'vestibular'` |
| `pais`      | text    | `'PT'`, `'BR'`, … default `'PT'` |
| `created_at`| tstz    | auto |

**Exemplo:**
```json
{"codigo": "mat-a", "nome": "Matemática A", "nivel": "secundario", "pais": "PT"}
```

---

### `fontes`

Uma linha por exame/prova. Ligada à matéria. Contém metadados estruturados extraídos da string legível.

| Coluna       | Tipo    | Notas |
|--------------|---------|-------|
| `id`         | uuid PK | auto |
| `materia_id` | uuid FK | → `materias.id` |
| `descricao`  | text    | string legível completa (única): `"Exame Nacional, Matemática A, 1.ª Fase, 2024"` |
| `tipo`       | text    | `'exame_nacional'` \| `'teste_intermedio'` \| `'vestibular'` \| `'enem'` \| `'concurso'` \| `'outro'` |
| `instituicao`| text    | `"IAVE"`, `"FUVEST"`, `"ENEM"`, null |
| `ano`        | integer | `2024`, `2023`, … |
| `fase`       | text    | `"1.ª Fase"`, `"2.ª Fase"`, `"Época Especial"`, null |
| `pais`       | text    | default `'PT'` |
| `url_pdf`    | text    | URL do PDF original (opcional) |
| `created_at` | tstz    | auto |

**Exemplo:**
```json
{
  "descricao": "Exame Nacional, Matemática A, 1.ª Fase, 2024",
  "tipo": "exame_nacional",
  "instituicao": "IAVE",
  "ano": 2024,
  "fase": "1.ª Fase",
  "pais": "PT"
}
```

---

### `topicos`

Taxonomia hierárquica controlada de tópicos por matéria.
**Nível 1** = tema geral (`"Funções"`)
**Nível 2** = subtema específico (`"Transformações de Funções"`, pai = `"Funções"`)

| Coluna       | Tipo    | Notas |
|--------------|---------|-------|
| `id`         | uuid PK | auto |
| `materia_id` | uuid FK | → `materias.id` |
| `nome`       | text    | `"Funções"`, `"Transformações de Funções"` |
| `slug`       | text    | URL-safe: `"funcoes"`, `"funcoes-transformacoes"` |
| `pai_id`     | uuid FK | → `topicos.id` (null = nível raiz) |
| `nivel`      | integer | `1` = tema, `2` = subtema |
| `created_at` | tstz    | auto |

**UNIQUE:** `(materia_id, slug)`

**Exemplo de árvore:**
```
Matemática A
├── Funções (nivel=1, slug="funcoes")
│   ├── Transformações de Funções (nivel=2, slug="funcoes-transformacoes")
│   └── Funções Racionais (nivel=2, slug="funcoes-racionais")
├── Probabilidade (nivel=1, slug="probabilidade")
│   ├── Probabilidade Condicional (nivel=2)
│   └── Combinatória (nivel=2)
└── Geometria Analítica (nivel=1)
    ├── Vetores no Espaço (nivel=2)
    └── Equações de Planos (nivel=2)
```

---

### `contextos`

Enunciados partilhados por grupos de sub-questões.

**Porquê existe esta tabela?**
Nas provas, é frequente um bloco de texto introdutório ser seguido de várias sub-questões (2.1, 2.2, 2.3) que o referenciam. Em vez de duplicar esse texto em cada sub-questão (como no schema v1 com `enunciado_contexto_pai`), existe uma linha nesta tabela que todas as sub-questões referenciam via `questoes.contexto_id`.

| Coluna              | Tipo  | Notas |
|---------------------|-------|-------|
| `id`                | uuid PK | auto |
| `fonte_id`          | uuid FK | → `fontes.id` |
| `texto`             | text  | Markdown/LaTeX do enunciado introdutório |
| `imagens`           | jsonb | `[{url, descricao, alt}]` — imagens do contexto |
| `grupo`             | text  | `"I"`, `"II"`, null — grupo da prova a que pertence |
| `id_item_original`  | text  | `"2"`, `"3"` — id do item context_stem na prova |
| `pagina_origem`     | int   | página no PDF |
| `created_at`        | tstz  | auto |

**UNIQUE:** `(fonte_id, id_item_original)`

**Exemplo de uso:**
```
contexto id=X: "Uma orquestra está a realizar audições…"
    ↑
questao id_item="2.1" → contexto_id=X
questao id_item="2.2" → contexto_id=X
questao id_item="2.3" → contexto_id=X
```

---

### `questoes`

Tabela principal. Contém apenas questões respondíveis (MC ou resposta aberta).
Os context stems foram removidos — são `contextos`, não questões.

| Coluna                    | Tipo     | Notas |
|---------------------------|----------|-------|
| **FKs** | | |
| `fonte_id`                | uuid FK  | → `fontes.id` NOT NULL |
| `contexto_id`             | uuid FK  | → `contextos.id` nullable |
| `topico_id`               | uuid FK  | → `topicos.id` nullable (subtópico canónico) |
| **Identificação** | | |
| `id_item`                 | text     | `"1"`, `"2.1"`, `"5.3"` — local à prova |
| `grupo`                   | text     | `"I"`, `"II"`, null |
| `numero_questao`          | integer  | ordem de apresentação |
| `subitem`                 | text     | `"1"` para `id_item="2.1"`, null para `"2"` |
| **Conteúdo** | | |
| `tipo_item`               | text     | `'multiple_choice'` \| `'open_response'` \| `'composite'` |
| `enunciado`               | text     | Markdown/LaTeX |
| `alternativas`            | jsonb    | `[{letra: "A", texto: "…"}, …]` |
| `imagens`                 | jsonb    | `[{url, descricao, alt}]` |
| **Resposta / CC** | | |
| `resposta_correta`        | text     | `"A"`–`"D"` para MC; null para abertas |
| `solucao`                 | text     | resolução completa em Markdown/LaTeX |
| `criterios_parciais`      | jsonb    | `[{pontos: N, descricao: "…"}]` |
| `resolucoes_alternativas` | jsonb    | `["Processo 2…", "Processo 3…"]` |
| `pontos_max`              | integer  | **auto-calculado** por trigger a partir de `criterios_parciais` |
| **Classificação (desnorm.)** | | |
| `materia`                 | text     | cópia de `materias.nome` — evita JOIN em listagens |
| `tema`                    | text     | cópia de `topicos(nivel=1).nome` |
| `subtema`                 | text     | cópia de `topicos(nivel=2).nome` |
| `tags`                    | text[]   | 3–5 tags livres |
| `descricao_breve`         | text     | resumo curto para preview |
| `dificuldade`             | text     | `'facil'` \| `'medio'` \| `'dificil'` (futuro) |
| `fonte`                   | text     | cópia de `fontes.descricao` — para filtro simples sem JOIN |
| **Busca** | | |
| `embedding`               | vector(1536) | pgvector; populado por job separado |
| `fts_doc`                 | tsvector | **auto-gerado** por trigger — busca full-text em português |
| **Metadados** | | |
| `pagina_origem`           | integer  | página no PDF |
| `status`                  | text     | `'approved'` \| `'approved_with_warnings'` \| `'pending_review'` \| `'error'` |
| `observacoes`             | text[]   | notas de pipeline |
| `created_at` / `updated_at` | tstz  | auto (trigger) |

**UNIQUE INDEX:** `(fonte_id, COALESCE(grupo, ''), id_item)`
O `COALESCE` é necessário porque dois NULL são distintos num UNIQUE constraint simples no PostgreSQL, o que causaria duplicados para provas sem grupos.

---

## Campo `imagens` — formato jsonb

```json
[
  {
    "url":       "https://<supabase>.supabase.co/storage/v1/object/public/questoes-media/EX-MatA635-F1-2024/fig1.png",
    "descricao": "Gráfico de função quadrática com vértice em (2, 3)",
    "alt":       "Figura 1"
  }
]
```

**Razão do formato jsonb vs text[]:**
- A `descricao` é usada pelo Gemini na revisão IA para compreender o contexto visual
- O `alt` é essencial para gerar PDFs acessíveis
- Facilita queries como `WHERE imagens @> '[{"alt":"Figura 1"}]'`

---

## Triggers automáticos

| Trigger | Tabela | Evento | Efeito |
|---------|--------|--------|--------|
| `trg_questoes_updated_at` | questoes | BEFORE UPDATE | actualiza `updated_at` |
| `trg_questoes_fts` | questoes | BEFORE INSERT/UPDATE | recalcula `fts_doc` |
| `trg_questoes_pontos` | questoes | BEFORE INSERT/UPDATE | recalcula `pontos_max` a partir de `criterios_parciais` |

### Campos que alimentam `fts_doc`
```sql
to_tsvector('portuguese',
  unaccent(enunciado) || ' ' ||
  unaccent(tema)      || ' ' ||
  unaccent(subtema)   || ' ' ||
  unaccent(descricao_breve) || ' ' ||
  unaccent(array_to_string(tags, ' '))
)
```

---

## Índices

| Índice | Tipo | Colunas | Uso |
|--------|------|---------|-----|
| `uq_questoes_fonte_grupo_item` | UNIQUE | `(fonte_id, COALESCE(grupo,''), id_item)` | unicidade / upsert |
| `idx_questoes_fonte_id` | btree | `fonte_id` | filtro por exame |
| `idx_questoes_topico_id` | btree | `topico_id` | filtro por tópico |
| `idx_questoes_tipo` | btree | `tipo_item` | filtro por tipo |
| `idx_questoes_materia` | btree | `materia` | filtro rápido |
| `idx_questoes_tema` | btree | `tema` | filtro rápido |
| `idx_questoes_subtema` | btree | `subtema` | filtro rápido |
| `idx_questoes_tags` | GIN | `tags` | operador `@>` em arrays |
| `idx_questoes_fts` | GIN | `fts_doc` | full-text search `@@` |
| `idx_questoes_embedding`* | HNSW | `embedding` | busca vetorial ANN |

\* Comentado na migração — activar após começar a popular embeddings.

---

## Views

### `v_questoes`
Vista completa com todos os metadados das tabelas normalizadas. Útil para o site frontend e para queries analíticas.

```sql
SELECT * FROM v_questoes
WHERE materia_nome = 'Matemática A'
  AND tema = 'Funções'
  AND fonte_ano = 2024;
```

### `v_topicos_stats`
Tópicos com contagem de questões — alimenta o menu de filtro do site.

```sql
SELECT * FROM v_topicos_stats
WHERE materia_codigo = 'mat-a' AND nivel = 1
ORDER BY total_questoes DESC;
```

### `v_fontes_stats`
Fontes com contagem por tipo de questão — útil para dashboards.

---

## Busca de Questões

### 1. Filtro heurístico (SQL puro)
```sql
-- Questões de funções do exame nacional 2024
SELECT * FROM questoes
WHERE materia = 'Matemática A'
  AND tema = 'Funções'
  AND fonte_id = (SELECT id FROM fontes WHERE ano = 2024 AND fase = '1.ª Fase')
ORDER BY numero_questao;
```

### 2. Full-text search
```sql
-- Questões que mencionam "probabilidade condicional"
SELECT *, ts_rank(fts_doc, query) AS rank
FROM questoes, to_tsquery('portuguese', 'probabilidade & condicional') AS query
WHERE fts_doc @@ query
ORDER BY rank DESC;
```

### 3. Busca semântica (requer embeddings populados)
```sql
-- Questões semanticamente similares a uma query embedding
SELECT id, enunciado, tema,
       embedding <=> '[0.1, 0.2, ...]'::vector AS distance
FROM questoes
ORDER BY distance
LIMIT 20;
```

---

## Geração de Quiz

Para montar um quiz completo com contextos partilhados:

```sql
-- Questões de um exame, com contexto pai quando aplicável
SELECT
  q.id_item,
  q.grupo,
  q.tipo_item,
  q.enunciado,
  q.alternativas,
  q.imagens,
  c.texto  AS contexto_texto,
  c.imagens AS contexto_imagens
FROM questoes q
LEFT JOIN contextos c ON c.id = q.contexto_id
WHERE q.fonte_id = '<uuid_do_exame>'
ORDER BY q.numero_questao, q.id_item;
```

---

## Extensões necessárias

| Extensão    | Função |
|-------------|--------|
| `uuid-ossp` | geração de UUIDs (`uuid_generate_v4()`) |
| `vector`    | pgvector — armazenamento e busca de embeddings |
| `unaccent`  | normalização de texto para FTS sem acentos |

Activar em: **Supabase Dashboard → Database → Extensions**

---

## Notas de Design

### Por que manter `materia`, `tema`, `subtema` e `fonte` desnormalizados em `questoes`?
Performance. Queries de listagem e filtro são feitas directamente sobre `questoes`. Fazer JOIN com `fontes → materias` e `topicos` em cada query seria mais lento. Os campos desnormalizados são mantidos sincronizados na escrita (pelo `supabase_client.py`).

### Por que `context_stem` não vai para `questoes`?
Um context stem não é uma questão — é um enunciado introdutório. Colocá-lo em `questoes` poluía as listagens e os quizzes com items não respondíveis. Com a tabela `contextos`, a relação é explícita e a reconstrução de um grupo de sub-questões é trivial.

### Por que `COALESCE(grupo, '')` no índice único?
PostgreSQL trata dois `NULL` como valores distintos num `UNIQUE` constraint simples. Sem o `COALESCE`, duas questões com `grupo=NULL` e o mesmo `id_item` num mesmo exame não colidiriam — gerando duplicados silenciosos.

### Embeddings (futuro)
O campo `embedding vector(1536)` está pronto para armazenar embeddings de 1536 dimensões (compatível com OpenAI `text-embedding-3-small` e outros). Um job separado (`module_embed.py`) será responsável por chamar a API de embeddings e populá-los. O índice HNSW está comentado na migração — deve ser criado apenas após ter dados suficientes (>1000 questões).
