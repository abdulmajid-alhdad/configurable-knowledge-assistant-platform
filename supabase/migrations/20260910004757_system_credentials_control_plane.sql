-- System Credentials control-plane boundary.
-- Secret references remain readable only inside protected database functions.

create function platform.list_credential_references(target_workspace uuid)
returns table(
  id uuid,
  workspace_id uuid,
  name text,
  provider_code text,
  status text,
  created_at timestamptz,
  updated_at timestamptz,
  reference_type text
)
language plpgsql security definer set search_path = '' as $$
begin
  if not platform.user_has_system_permission('credentials.read') then
    raise exception using errcode = '42501', message = 'CREDENTIAL_PERMISSION_DENIED';
  end if;

  return query
  select
    credential.id,
    credential.workspace_id,
    credential.name,
    credential.provider_code,
    credential.status,
    credential.created_at,
    credential.updated_at,
    case
      when credential.secret_reference like 'env:%' then 'env'
      when credential.secret_reference like 'vault:%' then 'vault'
      else 'unknown'
    end
  from platform.credential_references credential
  where credential.workspace_id = target_workspace
  order by credential.name;
end $$;

create or replace function platform.save_credential_reference(
  target_workspace uuid, reference_name text, target_provider text,
  target_reference text, new_status text
) returns uuid language plpgsql security definer set search_path = '' as $$
declare reference_id uuid;
begin
  if not platform.user_has_system_permission('credentials.manage') then
    raise exception using errcode = 'P0001', message = 'CREDENTIAL_PERMISSION_DENIED';
  end if;

  insert into platform.credential_references(
    workspace_id,name,provider_code,secret_reference,status,updated_by
  ) values (
    target_workspace,reference_name,target_provider,target_reference,new_status,
    platform.current_user_id()
  ) on conflict (workspace_id,name) do update set
    provider_code=excluded.provider_code,
    secret_reference=excluded.secret_reference,
    status=excluded.status,
    updated_by=excluded.updated_by,
    updated_at=now()
  returning id into reference_id;
  return reference_id;
end $$;

create or replace function platform.delete_credential_reference(
  target_workspace uuid, target_reference uuid
) returns boolean language plpgsql security definer set search_path = '' as $$
begin
  if not platform.user_has_system_permission('credentials.manage') then
    return false;
  end if;

  delete from platform.credential_references
  where workspace_id=target_workspace and id=target_reference;
  return found;
end $$;

revoke all on function platform.list_credential_references(uuid) from public;
revoke all on function platform.save_credential_reference(uuid,text,text,text,text) from public;
revoke all on function platform.delete_credential_reference(uuid,uuid) from public;

grant execute on function platform.list_credential_references(uuid)
  to knowledge_platform_runtime;
grant execute on function platform.save_credential_reference(uuid,text,text,text,text)
  to knowledge_platform_runtime;
grant execute on function platform.delete_credential_reference(uuid,uuid)
  to knowledge_platform_runtime;

-- The runtime must use the protected listing function rather than direct table
-- access. Revoke both broad and the historical safe-column SELECT grants.
revoke select on table platform.credential_references from knowledge_platform_runtime;
revoke select (id,workspace_id,name,provider_code,status,updated_by,created_at,updated_at)
  on table platform.credential_references from knowledge_platform_runtime;
