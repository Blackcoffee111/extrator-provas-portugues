-- =============================================================================
-- Migração 003: Campos adicionais para provas de Português
-- Aplica-se sobre o schema v2 existente — retrocompatível com Matemática A.
-- Todas as colunas são nullable / default vazio → não quebra linhas existentes.
-- =============================================================================

-- ── Novos campos em questoes ──────────────────────────────────────────────────

ALTER TABLE questoes
  ADD COLUMN IF NOT EXISTS pool_opcional         text,
  -- Pool de itens opcionais: "I-opt", "II-opt". NULL = item obrigatório.

  ADD COLUMN IF NOT EXISTS palavras_min          integer,
  -- Limite mínimo de palavras (Grupo III — texto dissertativo).

  ADD COLUMN IF NOT EXISTS palavras_max          integer,
  -- Limite máximo de palavras.

  ADD COLUMN IF NOT EXISTS linhas_referenciadas  text[]  NOT NULL DEFAULT '{}',
  -- Linhas do texto-âncora referenciadas no enunciado, ex. '{"16","29-30"}'.

  ADD COLUMN IF NOT EXISTS parametros_classificacao jsonb NOT NULL DEFAULT '[]';
  -- Parâmetros A/B/C de dissertação:
  -- [{"parametro":"A","nome":"Conteúdo","niveis":[{"nivel":"N5","pontos":12,"descritor":"..."},...]}]

-- ── Novos campos em contextos ─────────────────────────────────────────────────

ALTER TABLE contextos
  ADD COLUMN IF NOT EXISTS notas_rodape jsonb NOT NULL DEFAULT '[]';
  -- Notas de rodapé do excerto/texto-âncora:
  -- [{"numero":"1","texto":"calamistrar – tornar crespo ou frisado"}]

-- ── Índices auxiliares ────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_questoes_pool_opcional
  ON questoes (pool_opcional)
  WHERE pool_opcional IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_questoes_tipo_essay
  ON questoes (tipo_item)
  WHERE tipo_item IN ('essay', 'complete_table', 'multi_select');
