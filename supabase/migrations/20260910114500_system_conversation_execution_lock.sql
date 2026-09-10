-- Lock the SYSTEM conversation aggregate without granting the runtime role
-- direct UPDATE privilege on the table. The lock is held by the caller's
-- surrounding transaction until it commits or rolls back.

create function platform.lock_system_conversation_for_execution(
  target_conversation uuid
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  locked_conversation uuid;
begin
  if not platform.user_has_system_permission('system_conversations.read')
     or not platform.user_has_system_permission('system_conversations.create')
     or not platform.user_has_system_permission('system_workspaces.read')
     or not platform.user_has_system_permission('system_assistants.read')
     or not platform.user_has_system_permission('system_knowledge.read') then
    raise exception using errcode = '42501', message = 'permission denied';
  end if;

  select conversation.id
  into locked_conversation
  from platform.system_conversations as conversation
  where conversation.id = target_conversation
  for update;

  return found;
end;
$$;

revoke all on function platform.lock_system_conversation_for_execution(uuid)
  from public, anon, authenticated;
grant execute on function platform.lock_system_conversation_for_execution(uuid)
  to knowledge_platform_runtime;
