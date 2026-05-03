-- =============================================================================
-- Migração 004: Coluna respostas_corretas para multi_select / complete_table
-- Aplica-se sobre o schema v2 + migração 003 existentes — retrocompatível.
-- A coluna é nullable / default vazio → não quebra linhas existentes.
--
-- ⚠️  ORDEM DE APLICAÇÃO OBRIGATÓRIA:
--   1. Aplicar este SQL na base via Supabase SQL Editor.
--   2. NOTIFY pgrst, 'reload schema';   (força o PostgREST a refrescar o cache
--      OpenAPI — caso contrário o upload continua a receber HTTP 400 PGRST204
--      "column does not exist" mesmo com a coluna criada).
--   3. Só depois fazer deploy do código que envia o campo no payload.
--
-- Aplicar o código antes da SQL provoca falha de upload em batch para todas
-- as questões multi_select / complete_table (mesmo padrão de quebra que ocorreu
-- com migrações PT anteriores quando aplicadas fora de ordem).
-- =============================================================================

ALTER TABLE questoes
  ADD COLUMN IF NOT EXISTS respostas_corretas text[] NOT NULL DEFAULT '{}';
  -- Lista de respostas correctas para itens com múltiplas respostas:
  --   multi_select:    ["C", "E"]              (alternativas verdadeiras)
  --   complete_table:  ["3", "2"]              (opção por lacuna; ordem importa)
  --   complete_table:  ["a) 3", "b) 2"]       (variante com prefixo de lacuna)
  -- Vazio para outros tipos (multiple_choice usa resposta_correta singular).

-- Força o PostgREST a refrescar o cache de schema imediatamente.
-- Sem isto, mesmo com a coluna criada, o endpoint continua a rejeitar payloads
-- com `respostas_corretas` durante alguns segundos/minutos.
NOTIFY pgrst, 'reload schema';
