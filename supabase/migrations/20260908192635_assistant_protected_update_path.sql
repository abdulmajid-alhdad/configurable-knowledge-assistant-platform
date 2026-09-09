-- Protected SYSTEM-authority Assistant reconfiguration.
--
-- The runtime role intentionally has no direct UPDATE privilege on
-- platform.assistants.  This narrow function exposes only the mutable fields
-- accepted by the Assistant administration aggregate while preserving the
-- Assistant identity, Workspace ownership, and retrieval configuration.
create function platform.update_assistant_administration(
  target_workspace uuid,
  target_assistant uuid,
  requested_name text,
  requested_description text,
  requested_instructions text,
  requested_language text,
  requested_provider text,
  requested_model_reference text
) returns boolean
language plpgsql
security definer
set search_path = ''
as $assistant_protected_update$
declare
  changed_rows integer;
begin
  -- SYSTEM authority is derived exclusively from Stage 1 System access
  -- assignments and canonical SYSTEM permission scope.
  if not platform.user_has_system_permission('assistant.update') then
    raise exception using
      errcode = '42501',
      message = 'ASSISTANT_UPDATE_SYSTEM_PERMISSION_REQUIRED';
  end if;

  if target_workspace is null or target_assistant is null then
    raise exception using
      errcode = '22023',
      message = 'ASSISTANT_UPDATE_TARGET_REQUIRED';
  end if;

  if nullif(btrim(requested_name), '') is null
     or nullif(btrim(requested_instructions), '') is null
     or nullif(btrim(requested_language), '') is null
     or nullif(btrim(requested_provider), '') is null
     or nullif(btrim(requested_model_reference), '') is null
     or (requested_description is not null
         and nullif(btrim(requested_description), '') is null) then
    raise exception using
      errcode = '22023',
      message = 'ASSISTANT_UPDATE_INVALID_ARGUMENT';
  end if;

  update platform.assistants
  set name = btrim(requested_name),
      description = case
        when requested_description is null then null
        else btrim(requested_description)
      end,
      instructions = btrim(requested_instructions),
      language = btrim(requested_language),
      model_configuration = coalesce(model_configuration, '{}'::jsonb)
        || jsonb_build_object(
          'provider', btrim(requested_provider),
          'model_reference', btrim(requested_model_reference)
        )
  where id = target_assistant
    and workspace_id = target_workspace;

  get diagnostics changed_rows = row_count;
  if changed_rows <> 1 then
    raise exception using
      errcode = 'P0002',
      message = 'ASSISTANT_NOT_FOUND_IN_WORKSPACE';
  end if;

  perform platform.append_audit_event(
    target_workspace,
    'assistant.updated',
    'assistant',
    target_assistant,
    'succeeded',
    '',
    jsonb_build_object(
      'fields', jsonb_build_array(
        'name',
        'description',
        'instructions',
        'language',
        'provider',
        'model_reference'
      )
    )
  );

  return true;
end
$assistant_protected_update$;

comment on function platform.update_assistant_administration(
  uuid,uuid,text,text,text,text,text,text
) is 'SYSTEM-authorized, Workspace-bound Assistant administrative update';

-- Function execution is the only runtime mutation path. Browser database
-- roles and PUBLIC receive no execution privilege or table UPDATE privilege.
revoke all on function platform.update_assistant_administration(
  uuid,uuid,text,text,text,text,text,text
) from public;
revoke all on function platform.update_assistant_administration(
  uuid,uuid,text,text,text,text,text,text
) from anon, authenticated;
grant execute on function platform.update_assistant_administration(
  uuid,uuid,text,text,text,text,text,text
) to knowledge_platform_runtime;

revoke update on table platform.assistants from knowledge_platform_runtime;
revoke update on table platform.assistants from public, anon, authenticated;
