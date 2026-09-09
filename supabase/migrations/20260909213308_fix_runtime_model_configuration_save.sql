-- Fix the protected runtime-model save function after the canonical schema apply.
-- The RETURNS TABLE output parameter named capability makes an unqualified
-- capability reference ambiguous inside PL/pgSQL.

create or replace function platform.save_runtime_model_configuration(
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
  update platform.runtime_model_configuration_revisions as previous_revision
  set is_current = false
  where previous_revision.capability = requested_capability
    and previous_revision.is_current;

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

revoke all on function platform.save_runtime_model_configuration(
  text,text,text,text,text,integer,boolean,text
) from public;

grant execute on function platform.save_runtime_model_configuration(
  text,text,text,text,text,integer,boolean,text
) to knowledge_platform_runtime;
