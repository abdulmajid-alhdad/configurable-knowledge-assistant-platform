-- Stage 6C: explicit workspace-scoped assistant/source authorization.
create table platform.assistant_knowledge_sources (
    workspace_id uuid not null,
    assistant_id uuid not null references platform.assistants (id),
    knowledge_source_id uuid not null references platform.knowledge_sources (id),
    created_at timestamptz not null default now(),
    primary key (assistant_id, knowledge_source_id)
);

alter table platform.assistant_knowledge_sources enable row level security;
alter table platform.assistant_knowledge_sources force row level security;

create policy assistant_knowledge_sources_runtime_select
    on platform.assistant_knowledge_sources for select to knowledge_platform_runtime
    using (workspace_id = current_setting('app.workspace_id', true)::uuid);
create policy assistant_knowledge_sources_runtime_insert
    on platform.assistant_knowledge_sources for insert to knowledge_platform_runtime
    with check (workspace_id = current_setting('app.workspace_id', true)::uuid);
create policy assistant_knowledge_sources_runtime_delete
    on platform.assistant_knowledge_sources for delete to knowledge_platform_runtime
    using (workspace_id = current_setting('app.workspace_id', true)::uuid);

grant select, insert, delete on table platform.assistant_knowledge_sources
    to knowledge_platform_runtime;
