-- =============================================================================
-- Schema v2 — Exames Nacionais Pipeline
-- =============================================================================
-- Execute este ficheiro completo no SQL Editor do Supabase.
-- Apaga e recria tudo do zero (sem preservação de dados).
-- =============================================================================

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";       -- pgvector (habilitar em Dashboard → Extensions)
CREATE EXTENSION IF NOT EXISTS "unaccent";     -- para FTS sem acentos

-- ── Drop completo (ordem inversa das FKs) ─────────────────────────────────────
DROP TABLE IF EXISTS questoes   CASCADE;
DROP TABLE IF EXISTS contextos  CASCADE;
DROP TABLE IF EXISTS topicos    CASCADE;
DROP TABLE IF EXISTS fontes     CASCADE;
DROP TABLE IF EXISTS materias   CASCADE;

-- ── 1. materias ───────────────────────────────────────────────────────────────
-- Uma por disciplina: "Matemática A", "Física", "Química A", "História A", etc.
CREATE TABLE materias (
  id         uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  codigo     text        UNIQUE NOT NULL,  -- slug: "mat-a", "fisica-a", "enem-matematica"
  nome       text        UNIQUE NOT NULL,  -- legível: "Matemática A"
  nivel      text        NOT NULL DEFAULT 'secundario',
                         -- 'basico' | 'secundario' | 'universitario' | 'vestibular'
  pais       text        NOT NULL DEFAULT 'PT',
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ── 2. fontes ─────────────────────────────────────────────────────────────────
-- Um por exame/prova: "Exame Nacional, Matemática A, 1.ª Fase, 2024"
CREATE TABLE fontes (
  id          uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  materia_id  uuid        REFERENCES materias(id),
  descricao   text        UNIQUE NOT NULL,  -- string legível completa
  tipo        text        NOT NULL DEFAULT 'exame_nacional',
                          -- 'exame_nacional' | 'teste_intermedio' | 'vestibular'
                          -- | 'concurso' | 'enem' | 'outro'
  instituicao text,       -- "IAVE", "FUVEST", "ENEM", null
  ano         integer,
  fase        text,       -- "1.ª Fase", "2.ª Fase", "Época Especial", null
  pais        text        NOT NULL DEFAULT 'PT',
  url_pdf     text,       -- URL do PDF original, se disponível
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ── 3. topicos ────────────────────────────────────────────────────────────────
-- Taxonomia hierárquica controlada: tema → subtema
-- Permite UI de filtro em árvore (ex: Matemática A > Funções > Transformações)
CREATE TABLE topicos (
  id         uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  materia_id uuid        NOT NULL REFERENCES materias(id),
  nome       text        NOT NULL,   -- "Funções", "Transformações de Funções"
  slug       text        NOT NULL,   -- "funcoes", "funcoes-transformacoes"
  pai_id     uuid        REFERENCES topicos(id),  -- null = nível raiz (tema)
  nivel      integer     NOT NULL DEFAULT 1,      -- 1 = tema, 2 = subtema
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(materia_id, slug)
);

-- ── 4. contextos ──────────────────────────────────────────────────────────────
-- Enunciados partilhados por grupos de sub-questões.
-- Ex: a questão 2 de um exame tem sub-questões 2.1, 2.2, 2.3 que partilham
-- um texto introdutório e possivelmente imagens.
-- Substitui o campo enunciado_contexto_pai duplicado em cada sub-questão.
CREATE TABLE contextos (
  id               uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
  fonte_id         uuid        NOT NULL REFERENCES fontes(id),
  texto            text        NOT NULL DEFAULT '',  -- Markdown/LaTeX do contexto
  imagens          jsonb       NOT NULL DEFAULT '[]',
                               -- [{url, descricao, alt}]
  grupo            text,       -- "I", "II" — null se a prova não tem grupos
  id_item_original text,       -- "2", "3" — id_item do context_stem de origem
  pagina_origem    integer,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE(fonte_id, id_item_original)
);

-- ── 5. questoes ───────────────────────────────────────────────────────────────
CREATE TABLE questoes (
  id           uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),

  -- Chaves estrangeiras
  fonte_id     uuid        NOT NULL REFERENCES fontes(id),
  contexto_id  uuid        REFERENCES contextos(id),  -- null = questão independente
  topico_id    uuid        REFERENCES topicos(id),    -- subtópico canónico (opcional)

  -- Identificação
  id_item          text    NOT NULL,  -- "1", "2.1", "5.3"
  grupo            text,              -- "I", "II" — null se sem grupos
  numero_questao   integer,           -- ordem de apresentação
  subitem          text,              -- "1" para id_item "2.1"; null para "2"

  -- Conteúdo
  tipo_item    text        NOT NULL DEFAULT 'unknown',
               -- 'multiple_choice' | 'open_response' | 'composite'
               -- (context_stem vão para contextos, não questoes)
  enunciado    text        NOT NULL DEFAULT '',  -- Markdown/LaTeX
  alternativas jsonb       NOT NULL DEFAULT '[]',
               -- [{letra: "A", texto: "..."}, ...]
  imagens      jsonb       NOT NULL DEFAULT '[]',
               -- [{url: "https://...", descricao: "...", alt: "Fig. 1"}]

  -- Resposta e Critérios de Classificação
  resposta_correta        text,   -- "A"–"D" para MC; null para abertas
  solucao                 text    NOT NULL DEFAULT '',
  criterios_parciais      jsonb   NOT NULL DEFAULT '[]',
                          -- [{pontos: N, descricao: "..."}]
  resolucoes_alternativas jsonb   NOT NULL DEFAULT '[]',
                          -- ["Processo 2...", "Processo 3..."]
  pontos_max              integer,  -- soma de criterios_parciais.pontos

  -- Classificação (desnormalizado para performance — evita JOINs em listagens)
  materia      text        NOT NULL DEFAULT '',  -- cópia de materias.nome
  tema         text        NOT NULL DEFAULT '',  -- cópia de topicos(nivel=1).nome
  subtema      text        NOT NULL DEFAULT '',  -- cópia de topicos(nivel=2).nome
  tags         text[]      NOT NULL DEFAULT '{}',
  descricao_breve text     NOT NULL DEFAULT '',
  dificuldade  text,  -- 'facil' | 'medio' | 'dificil' (preenchido futuramente)

  -- Campo legível desnormalizado (para filtros/display sem JOIN)
  fonte        text        NOT NULL DEFAULT '',  -- cópia de fontes.descricao

  -- Busca semântica e full-text
  embedding    vector(1536),  -- pgvector; populado por job separado
  fts_doc      tsvector,      -- populado por trigger abaixo

  -- Metadados
  pagina_origem  integer,
  status         text        NOT NULL DEFAULT 'approved',
                 -- 'approved' | 'approved_with_warnings' | 'pending_review' | 'error'
  observacoes    text[]      NOT NULL DEFAULT '{}',
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

-- Unique index com COALESCE para tratar NULL em grupo como string vazia
-- (PostgreSQL trata dois NULLs como distintos num UNIQUE constraint simples)
CREATE UNIQUE INDEX uq_questoes_fonte_grupo_item
  ON questoes (fonte_id, COALESCE(grupo, ''), id_item);

-- ── Índices ────────────────────────────────────────────────────────────────────

-- Filtros principais (heurístico)
CREATE INDEX idx_questoes_fonte_id    ON questoes (fonte_id);
CREATE INDEX idx_questoes_contexto_id ON questoes (contexto_id);
CREATE INDEX idx_questoes_topico_id   ON questoes (topico_id);
CREATE INDEX idx_questoes_tipo        ON questoes (tipo_item);
CREATE INDEX idx_questoes_materia     ON questoes (materia);
CREATE INDEX idx_questoes_tema        ON questoes (tema);
CREATE INDEX idx_questoes_subtema     ON questoes (subtema);
CREATE INDEX idx_questoes_dificuldade ON questoes (dificuldade);
CREATE INDEX idx_questoes_fonte_txt   ON questoes (fonte);  -- filtro legível

-- Tags (GIN para @> e operadores de array)
CREATE INDEX idx_questoes_tags ON questoes USING GIN (tags);

-- Full-text search (GIN)
CREATE INDEX idx_questoes_fts ON questoes USING GIN (fts_doc);

-- Busca semântica — HNSW (rápido para approximate nearest neighbor)
-- Só activar após começar a popular embeddings
-- CREATE INDEX idx_questoes_embedding ON questoes
--   USING hnsw (embedding vector_cosine_ops)
--   WITH (m = 16, ef_construction = 64);

-- Índices auxiliares
CREATE INDEX idx_fontes_materia_id  ON fontes  (materia_id);
CREATE INDEX idx_fontes_ano         ON fontes  (ano);
CREATE INDEX idx_topicos_materia_id ON topicos (materia_id);
CREATE INDEX idx_topicos_pai_id     ON topicos (pai_id);
CREATE INDEX idx_contextos_fonte_id ON contextos (fonte_id);

-- ── Triggers ───────────────────────────────────────────────────────────────────

-- updated_at automático
CREATE OR REPLACE FUNCTION _update_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_questoes_updated_at
  BEFORE UPDATE ON questoes
  FOR EACH ROW EXECUTE FUNCTION _update_updated_at();

-- fts_doc: gera tsvector a partir de enunciado + tema + subtema + descricao_breve + tags
CREATE OR REPLACE FUNCTION _update_questao_fts()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.fts_doc := to_tsvector('portuguese',
    unaccent(coalesce(NEW.enunciado,       '')) || ' ' ||
    unaccent(coalesce(NEW.tema,            '')) || ' ' ||
    unaccent(coalesce(NEW.subtema,         '')) || ' ' ||
    unaccent(coalesce(NEW.descricao_breve, '')) || ' ' ||
    unaccent(coalesce(array_to_string(NEW.tags, ' '), ''))
  );
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_questoes_fts
  BEFORE INSERT OR UPDATE ON questoes
  FOR EACH ROW EXECUTE FUNCTION _update_questao_fts();

-- pontos_max: calculado automaticamente a partir de criterios_parciais
CREATE OR REPLACE FUNCTION _update_questao_pontos()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  total integer := 0;
  cp    jsonb;
BEGIN
  IF NEW.criterios_parciais IS NOT NULL AND jsonb_array_length(NEW.criterios_parciais) > 0 THEN
    FOR cp IN SELECT * FROM jsonb_array_elements(NEW.criterios_parciais) LOOP
      total := total + COALESCE((cp->>'pontos')::integer, 0);
    END LOOP;
    NEW.pontos_max := total;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_questoes_pontos
  BEFORE INSERT OR UPDATE ON questoes
  FOR EACH ROW EXECUTE FUNCTION _update_questao_pontos();

-- ── Views úteis ────────────────────────────────────────────────────────────────

-- Vista completa com metadados das tabelas normalizadas
CREATE OR REPLACE VIEW v_questoes AS
SELECT
  q.*,
  f.ano              AS fonte_ano,
  f.fase             AS fonte_fase,
  f.tipo             AS fonte_tipo,
  f.instituicao      AS fonte_instituicao,
  f.url_pdf          AS fonte_url_pdf,
  m.codigo           AS materia_codigo,
  m.nivel            AS materia_nivel,
  m.pais             AS materia_pais,
  t.nome             AS topico_nome,
  t.slug             AS topico_slug,
  tp.nome            AS tema_nome,   -- pai do topico (nivel=1)
  c.texto            AS contexto_texto,
  c.imagens          AS contexto_imagens
FROM questoes q
JOIN fontes   f  ON f.id = q.fonte_id
JOIN materias m  ON m.id = f.materia_id
LEFT JOIN topicos  t  ON t.id  = q.topico_id
LEFT JOIN topicos  tp ON tp.id = t.pai_id
LEFT JOIN contextos c ON c.id  = q.contexto_id;

-- Vista de tópicos com contagem de questões
CREATE OR REPLACE VIEW v_topicos_stats AS
SELECT
  t.id,
  t.nome,
  t.slug,
  t.nivel,
  t.pai_id,
  tp.nome   AS pai_nome,
  m.nome    AS materia_nome,
  m.codigo  AS materia_codigo,
  COUNT(q.id) AS total_questoes
FROM topicos t
JOIN materias m ON m.id = t.materia_id
LEFT JOIN topicos tp ON tp.id = t.pai_id
LEFT JOIN questoes q ON q.topico_id = t.id
GROUP BY t.id, t.nome, t.slug, t.nivel, t.pai_id, tp.nome, m.nome, m.codigo;

-- Vista de fontes com contagem
CREATE OR REPLACE VIEW v_fontes_stats AS
SELECT
  f.id,
  f.descricao,
  f.tipo,
  f.ano,
  f.fase,
  f.instituicao,
  m.nome AS materia_nome,
  COUNT(q.id) AS total_questoes,
  SUM(CASE WHEN q.tipo_item = 'multiple_choice' THEN 1 ELSE 0 END) AS total_mc,
  SUM(CASE WHEN q.tipo_item = 'open_response'   THEN 1 ELSE 0 END) AS total_rd
FROM fontes f
JOIN materias m ON m.id = f.materia_id
LEFT JOIN questoes q ON q.fonte_id = f.id
GROUP BY f.id, f.descricao, f.tipo, f.ano, f.fase, f.instituicao, m.nome;
