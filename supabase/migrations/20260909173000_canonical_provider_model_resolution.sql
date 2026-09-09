-- Canonical global runtime provider/model configuration.
-- Configuration revisions contain references only; no credential values.

-- OpenRouter is backed by both remote adapters in the current platform.
update platform.provider_registry
set provider_type = 'multi', updated_at = now()
where code = 'openrouter' and provider_type <> 'multi';

create table platform.runtime_model_configuration_revisions (
  id uuid primary key default gen_random_uuid(),
  capability text not null check (capability in ('generation', 'embedding')),
  provider_code text not null references platform.provider_registry(code),
  model_identifier text not null check (
    char_length(btrim(model_identifier)) between 1 and 240
  ),
  endpoint text not null check (endpoint ~ '^https://[^[:space:]]+$'),
  credential_reference text not null check (
    credential_reference ~ '^[A-Z][A-Z0-9_]{1,79}$'
  ),
  embedding_dimensions integer,
  active boolean not null,
  is_current boolean not null default true,
  created_by uuid not null references auth.users(id),
  request_id text,
  created_at timestamptz not null default now(),
  check (
    (capability = 'generation' and embedding_dimensions is null)
    or
    (capability = 'embedding' and embedding_dimensions between 1 and 65536)
  )
);

create unique index runtime_model_configuration_current_capability_idx
  on platform.runtime_model_configuration_revisions(capability)
  where is_current;
create index runtime_model_configuration_history_idx
  on platform.runtime_model_configuration_revisions(capability, created_at desc, id);

alter table platform.runtime_model_configuration_revisions enable row level security;
alter table platform.runtime_model_configuration_revisions force row level security;

revoke all on platform.runtime_model_configuration_revisions
  from public, anon, authenticated, knowledge_platform_runtime;

create function platform.list_runtime_provider_catalogue()
returns table(
  code text,
  display_name text,
  provider_type text,
  base_url text
)
language sql
security definer
stable
set search_path = ''
as $$
  select provider.code, provider.display_name, provider.provider_type,
         provider.base_url
  from platform.provider_registry provider
  order by lower(provider.display_name), provider.code
$$;

create function platform.get_runtime_model_configuration(
  requested_capability text
)
returns table(
  id uuid,
  capability text,
  provider_code text,
  model_identifier text,
  endpoint text,
  credential_reference text,
  embedding_dimensions integer,
  active boolean,
  created_by uuid,
  created_at timestamptz
)
language plpgsql
security definer
stable
set search_path = ''
as $$
begin
  if requested_capability not in ('generation', 'embedding') then
    raise exception using errcode = '22023', message = 'MODEL_CAPABILITY_INVALID';
  end if;
  return query
  select revision.id, revision.capability, revision.provider_code,
         revision.model_identifier, revision.endpoint,
         revision.credential_reference, revision.embedding_dimensions,
         revision.active, revision.created_by, revision.created_at
  from platform.runtime_model_configuration_revisions revision
  where revision.capability = requested_capability and revision.is_current;
end $$;

create function platform.save_runtime_model_configuration(
  requested_capability text,
  requested_provider text,
  requested_model text,
  requested_endpoint text,
  requested_credential_reference text,
  requested_dimensions integer,
  requested_active boolean,
  requested_request_id text default null
)
returns table(
  id uuid,
  capability text,
  provider_code text,
  model_identifier text,
  endpoint text,
  credential_reference text,
  embedding_dimensions integer,
  active boolean,
  created_by uuid,
  created_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  provider_kind text;
  actor uuid;
  revision_id uuid;
begin
  if not platform.user_has_system_permission('providers.manage') then
    raise exception using errcode = '42501', message = 'PROVIDER_CONFIGURATION_FORBIDDEN';
  end if;
  actor := platform.current_user_id();
  if actor is null then
    raise exception using errcode = '42501', message = 'PROVIDER_CONFIGURATION_ACTOR_REQUIRED';
  end if;
  if requested_capability not in ('generation', 'embedding') then
    raise exception using errcode = '22023', message = 'MODEL_CAPABILITY_INVALID';
  end if;
  if requested_model is null or char_length(btrim(requested_model)) not between 1 and 240 then
    raise exception using errcode = '22023', message = 'MODEL_IDENTIFIER_INVALID';
  end if;
  if requested_endpoint is null or requested_endpoint !~ '^https://[^[:space:]]+$' then
    raise exception using errcode = '22023', message = 'REMOTE_HTTPS_ENDPOINT_REQUIRED';
  end if;
  if requested_credential_reference is null
     or requested_credential_reference !~ '^[A-Z][A-Z0-9_]{1,79}$' then
    raise exception using errcode = '22023', message = 'CREDENTIAL_REFERENCE_INVALID';
  end if;
  if requested_capability = 'embedding'
     and (requested_dimensions is null or requested_dimensions not between 1 and 65536) then
    raise exception using errcode = '22023', message = 'EMBEDDING_DIMENSIONS_INVALID';
  end if;
  if requested_capability = 'generation' and requested_dimensions is not null then
    raise exception using errcode = '22023', message = 'GENERATION_DIMENSIONS_UNSUPPORTED';
  end if;

  select provider.provider_type into provider_kind
  from platform.provider_registry provider
  where provider.code = requested_provider;
  if provider_kind is null then
    raise exception using errcode = '22023', message = 'UNSUPPORTED_PROVIDER';
  end if;
  if (requested_capability = 'generation' and provider_kind not in ('generation', 'multi'))
     or (requested_capability = 'embedding' and provider_kind not in ('embeddings', 'multi')) then
    raise exception using errcode = '22023', message = 'PROVIDER_CAPABILITY_MISMATCH';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended('runtime-model-configuration:' || requested_capability, 0)
  );
  update platform.runtime_model_configuration_revisions
  set is_current = false
  where capability = requested_capability and is_current;

  insert into platform.runtime_model_configuration_revisions(
    capability, provider_code, model_identifier, endpoint,
    credential_reference, embedding_dimensions, active, created_by, request_id
  ) values (
    requested_capability, requested_provider, btrim(requested_model),
    requested_endpoint, requested_credential_reference, requested_dimensions,
    requested_active, actor, nullif(requested_request_id, '')
  ) returning runtime_model_configuration_revisions.id into revision_id;

  return query
  select revision.id, revision.capability, revision.provider_code,
         revision.model_identifier, revision.endpoint,
         revision.credential_reference, revision.embedding_dimensions,
         revision.active, revision.created_by, revision.created_at
  from platform.runtime_model_configuration_revisions revision
  where revision.id = revision_id;
end $$;

revoke all on function platform.list_runtime_provider_catalogue() from public;
revoke all on function platform.get_runtime_model_configuration(text) from public;
revoke all on function platform.save_runtime_model_configuration(
  text,text,text,text,text,integer,boolean,text
) from public;

grant execute on function platform.list_runtime_provider_catalogue(),
  platform.get_runtime_model_configuration(text),
  platform.save_runtime_model_configuration(
    text,text,text,text,text,integer,boolean,text
  ) to knowledge_platform_runtime;
