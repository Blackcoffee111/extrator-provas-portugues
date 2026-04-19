-- Patch: substituir índice funcional por UNIQUE constraint real
-- Necessário para que o PostgREST aceite on_conflict=fonte_id,grupo,id_item

DROP INDEX IF EXISTS uq_questoes_fonte_grupo_item;

ALTER TABLE questoes ALTER COLUMN grupo SET NOT NULL;
ALTER TABLE questoes ALTER COLUMN grupo SET DEFAULT '';
UPDATE questoes SET grupo = '' WHERE grupo IS NULL;

ALTER TABLE questoes
  ADD CONSTRAINT uq_questoes_fonte_grupo_item
  UNIQUE (fonte_id, grupo, id_item);
