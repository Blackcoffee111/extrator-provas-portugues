-- =============================================================================
-- Migração 001: Tabela questoes
-- Pipeline Exames Nacionais → Supabase
-- =============================================================================

-- Habilita extensão uuid
create extension if not exists "uuid-ossp";

-- Tabela principal de questões
create table if not exists questoes (
  id             uuid primary key default uuid_generate_v4(),

  -- Identificação
  id_item        text    not null,                 -- "1", "2.1", "5.3"
  numero_questao integer not null,
  ordem_item     integer,
  numero_principal integer,
  subitem        text,                             -- "1", "2", null

  -- Conteúdo
  enunciado      text    not null default '',
  alternativas   jsonb   not null default '[]',    -- [{letra, texto}]
  tipo_item      text    not null default 'unknown',

  -- Classificação
  materia        text    not null default '',
  tema           text    not null default '',
  subtema        text    not null default '',
  tags           text[]  not null default '{}',
  descricao_breve text   not null default '',

  -- Imagens
  imagens        text[]  not null default '{}',    -- URLs públicas
  imagens_contexto text[] not null default '{}',
  descricoes_imagens jsonb not null default '{}',

  -- Resposta / Critérios de Classificação
  resposta_correta text,                           -- "C" para MC; null para aberta
  solucao          text   not null default '',      -- resolução completa Markdown/LaTeX
  criterios_parciais jsonb not null default '[]',   -- [{pontos, descricao}]
  resolucoes_alternativas jsonb not null default '[]', -- ["processo 2 ...", ...]

  -- Contexto do enunciado (pai de subitems)
  enunciado_contexto_pai text not null default '',

  -- Metadados
  fonte          text    not null default '',       -- "Exame Nacional, Matemática A, 1.ª Fase, 2024"
  pagina_origem  integer,
  status         text    not null default 'approved',
  observacoes    text[]  not null default '{}',

  -- Timestamps
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),

  -- Constraint de unicidade: mesmo exame + mesmo item = mesma questão
  constraint uq_fonte_item unique (fonte, id_item)
);

-- Índices para consultas comuns
create index if not exists idx_questoes_fonte     on questoes (fonte);
create index if not exists idx_questoes_tipo      on questoes (tipo_item);
create index if not exists idx_questoes_tema      on questoes (tema);
create index if not exists idx_questoes_subtema   on questoes (subtema);
create index if not exists idx_questoes_tags      on questoes using gin (tags);
create index if not exists idx_questoes_materia   on questoes (materia);

-- Trigger para updated_at automático
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_questoes_updated_at on questoes;
create trigger trg_questoes_updated_at
  before update on questoes
  for each row execute function update_updated_at();

-- RLS (Row Level Security) — desactivar por default para uso via service_role key
-- Se quiser habilitar depois: alter table questoes enable row level security;

-- Storage bucket (executar manualmente no dashboard Supabase ou via API):
-- insert into storage.buckets (id, name, public) values ('questoes-media', 'questoes-media', true);
