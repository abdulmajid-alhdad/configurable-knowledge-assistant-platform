-- C2-06: persist workspace-owned conversations and append-only messages.
create table platform.conversations (
    id uuid primary key,
    workspace_id uuid not null references platform.workspaces (id),
    assistant_id uuid not null references platform.assistants (id)
);

create table platform.messages (
    conversation_id uuid not null references platform.conversations (id),
    sequence integer not null,
    role text not null,
    content text not null,
    primary key (conversation_id, sequence),
    constraint messages_sequence_nonnegative check (sequence >= 0),
    constraint messages_role_vocabulary check (role in ('user', 'assistant')),
    constraint messages_content_nonblank check (btrim(content) <> '')
);

alter table platform.conversations enable row level security;
alter table platform.conversations force row level security;
alter table platform.messages enable row level security;
alter table platform.messages force row level security;

create policy conversations_runtime_select on platform.conversations
    for select to knowledge_platform_runtime
    using (workspace_id = current_setting('app.workspace_id', true)::uuid);
create policy conversations_runtime_insert on platform.conversations
    for insert to knowledge_platform_runtime
    with check (workspace_id = current_setting('app.workspace_id', true)::uuid);

create policy messages_runtime_select on platform.messages
    for select to knowledge_platform_runtime
    using (conversation_id in (
        select id from platform.conversations
        where workspace_id = current_setting('app.workspace_id', true)::uuid
    ));
create policy messages_runtime_insert on platform.messages
    for insert to knowledge_platform_runtime
    with check (conversation_id in (
        select id from platform.conversations
        where workspace_id = current_setting('app.workspace_id', true)::uuid
    ));

grant select, insert on table platform.conversations to knowledge_platform_runtime;
grant select, insert on table platform.messages to knowledge_platform_runtime;
