-- C2-05: persist workspace-owned KnowledgeSource lifecycle state.
create table platform.knowledge_sources (
    id uuid primary key,
    workspace_id uuid not null references platform.workspaces (id),
    name text not null,
    kind text not null,
    lifecycle text not null,
    constraint knowledge_sources_name_nonblank check (btrim(name) <> ''),
    constraint knowledge_sources_kind_vocabulary check (kind in ('document', 'structured')),
    constraint knowledge_sources_lifecycle_vocabulary check (
        lifecycle in ('registered', 'preparing', 'ready', 'disabled', 'failed', 'removing', 'removed')
    )
);

alter table platform.knowledge_sources enable row level security;
alter table platform.knowledge_sources force row level security;

create policy knowledge_sources_runtime_select on platform.knowledge_sources
    for select to knowledge_platform_runtime
    using (workspace_id = current_setting('app.workspace_id', true)::uuid);

create policy knowledge_sources_runtime_insert on platform.knowledge_sources
    for insert to knowledge_platform_runtime
    with check (workspace_id = current_setting('app.workspace_id', true)::uuid);

create policy knowledge_sources_runtime_update on platform.knowledge_sources
    for update to knowledge_platform_runtime
    using (workspace_id = current_setting('app.workspace_id', true)::uuid)
    with check (workspace_id = current_setting('app.workspace_id', true)::uuid);

create policy knowledge_sources_runtime_delete on platform.knowledge_sources
    for delete to knowledge_platform_runtime
    using (workspace_id = current_setting('app.workspace_id', true)::uuid);

grant select, insert, update on table platform.knowledge_sources
    to knowledge_platform_runtime;
