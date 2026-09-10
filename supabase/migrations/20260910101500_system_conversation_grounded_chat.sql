-- Grounded SYSTEM conversations remain distinct from Workspace conversations.
-- Historical rows may remain unbound; all new runtime inserts require a bound
-- Workspace/Assistant pair through the policy below.

alter table platform.system_conversations
  add column workspace_id uuid,
  add column assistant_id uuid,
  add constraint system_conversations_binding_complete_or_legacy check(
    (workspace_id is null) = (assistant_id is null)
  ),
  add constraint system_conversations_assistant_workspace_fk
    foreign key(assistant_id,workspace_id)
    references platform.assistants(id,workspace_id);

create index system_conversations_workspace_assistant_updated_idx
  on platform.system_conversations(workspace_id,assistant_id,updated_at desc,id)
  where workspace_id is not null;

alter table platform.system_conversation_messages
  add column outcome text,
  add constraint system_conversation_messages_outcome_vocabulary check(
    outcome is null or outcome in (
      'grounded','insufficient_evidence','policy_denied','technical_failure'
    )
  ),
  add constraint system_conversation_messages_assistant_outcome_only check(
    outcome is null or role='assistant'
  );

create table platform.system_conversation_message_evidence(
  conversation_id uuid not null,
  message_sequence integer not null,
  ordinal integer not null,
  source_id uuid not null references platform.knowledge_sources(id),
  content text not null,
  provenance_locator text not null,
  primary key(conversation_id,message_sequence,ordinal),
  constraint system_conversation_message_evidence_message_fk
    foreign key(conversation_id,message_sequence)
    references platform.system_conversation_messages(conversation_id,sequence),
  constraint system_conversation_message_evidence_ordinal_positive check(ordinal>0),
  constraint system_conversation_message_evidence_content_nonblank check(btrim(content)<>''),
  constraint system_conversation_message_evidence_provenance_nonblank
    check(btrim(provenance_locator)<>'')
);

create function platform.touch_system_conversation_updated_at()
returns trigger language plpgsql security definer set search_path='' as $$
begin
  update platform.system_conversations
  set updated_at=now()
  where id=new.conversation_id;
  return new;
end $$;

create trigger system_conversation_messages_touch_parent
after insert on platform.system_conversation_messages
for each row execute function platform.touch_system_conversation_updated_at();

alter table platform.system_conversation_message_evidence enable row level security;
alter table platform.system_conversation_message_evidence force row level security;

drop policy if exists system_conversations_runtime_select on platform.system_conversations;
create policy system_conversations_runtime_select
on platform.system_conversations for select to knowledge_platform_runtime
using(
  platform.user_has_system_permission('system_conversations.read')
  and (
    workspace_id is null
    or (
      platform.user_has_system_permission('system_workspaces.read')
      and platform.user_has_system_permission('system_assistants.read')
      and platform.user_has_system_permission('system_knowledge.read')
    )
  )
);

drop policy if exists system_conversations_runtime_insert on platform.system_conversations;
create policy system_conversations_runtime_insert
on platform.system_conversations for insert to knowledge_platform_runtime
with check(
  platform.user_has_system_permission('system_conversations.create')
  and platform.user_has_system_permission('system_workspaces.read')
  and platform.user_has_system_permission('system_assistants.read')
  and workspace_id is not null
  and assistant_id is not null
  and created_by=platform.current_user_id()
);

drop policy if exists system_conversation_messages_runtime_select
  on platform.system_conversation_messages;
create policy system_conversation_messages_runtime_select
on platform.system_conversation_messages for select to knowledge_platform_runtime
using(
  platform.user_has_system_permission('system_conversations.read')
  and exists(
    select 1 from platform.system_conversations conversation
    where conversation.id=system_conversation_messages.conversation_id
      and (
        conversation.workspace_id is null
        or (
          platform.user_has_system_permission('system_workspaces.read')
          and platform.user_has_system_permission('system_assistants.read')
          and platform.user_has_system_permission('system_knowledge.read')
        )
      )
  )
);

drop policy if exists system_conversation_messages_runtime_insert
  on platform.system_conversation_messages;
create policy system_conversation_messages_runtime_insert
on platform.system_conversation_messages for insert to knowledge_platform_runtime
with check(
  platform.user_has_system_permission('system_conversations.create')
  and platform.user_has_system_permission('system_conversations.read')
  and platform.user_has_system_permission('system_workspaces.read')
  and platform.user_has_system_permission('system_assistants.read')
  and platform.user_has_system_permission('system_knowledge.read')
  and exists(
    select 1 from platform.system_conversations conversation
    where conversation.id=system_conversation_messages.conversation_id
      and conversation.status='ACTIVE'
      and conversation.workspace_id is not null
      and conversation.assistant_id is not null
  )
);

create policy system_conversation_message_evidence_runtime_select
on platform.system_conversation_message_evidence for select to knowledge_platform_runtime
using(
  platform.user_has_system_permission('system_conversations.read')
  and platform.user_has_system_permission('system_workspaces.read')
  and platform.user_has_system_permission('system_assistants.read')
  and platform.user_has_system_permission('system_knowledge.read')
  and exists(
    select 1 from platform.system_conversations conversation
    where conversation.id=system_conversation_message_evidence.conversation_id
      and conversation.workspace_id is not null
  )
);

create policy system_conversation_message_evidence_runtime_insert
on platform.system_conversation_message_evidence for insert to knowledge_platform_runtime
with check(
  platform.user_has_system_permission('system_conversations.create')
  and platform.user_has_system_permission('system_conversations.read')
  and platform.user_has_system_permission('system_workspaces.read')
  and platform.user_has_system_permission('system_assistants.read')
  and platform.user_has_system_permission('system_knowledge.read')
  and exists(
    select 1
    from platform.system_conversations conversation
    join platform.knowledge_sources source
      on source.id=system_conversation_message_evidence.source_id
     and source.workspace_id=conversation.workspace_id
    join platform.system_conversation_messages message
      on message.conversation_id=conversation.id
     and message.sequence=system_conversation_message_evidence.message_sequence
     and message.role='assistant'
     and message.outcome='grounded'
    where conversation.id=system_conversation_message_evidence.conversation_id
      and conversation.status='ACTIVE'
      and conversation.workspace_id is not null
      and conversation.assistant_id is not null
  )
);

grant select,insert on platform.system_conversation_message_evidence
  to knowledge_platform_runtime;
revoke all on platform.system_conversation_message_evidence from anon,authenticated;

revoke all on function platform.touch_system_conversation_updated_at() from public;
