-- C2-04: persist Workspace and Assistant with workspace-scoped RLS.
create table platform.workspaces (
    id uuid primary key,
    name text not null,
    constraint workspaces_name_nonblank check (btrim(name) <> '')
);

create table platform.assistants (
    id uuid primary key,
    workspace_id uuid not null references platform.workspaces (id),
    name text not null,
    description text,
    instructions text not null,
    language text not null,
    model_configuration jsonb not null,
    retrieval_configuration jsonb not null,
    constraint assistants_name_nonblank check (btrim(name) <> ''),
    constraint assistants_instructions_nonblank check (btrim(instructions) <> ''),
    constraint assistants_language_nonblank check (btrim(language) <> '')
);

alter table platform.workspaces enable row level security;
alter table platform.workspaces force row level security;
alter table platform.assistants enable row level security;
alter table platform.assistants force row level security;

create policy workspaces_runtime_select on platform.workspaces
    for select to knowledge_platform_runtime
    using (id = current_setting('app.workspace_id', true)::uuid);

create policy workspaces_runtime_insert on platform.workspaces
    for insert to knowledge_platform_runtime
    with check (id = current_setting('app.workspace_id', true)::uuid);

create policy workspaces_runtime_update on platform.workspaces
    for update to knowledge_platform_runtime
    using (id = current_setting('app.workspace_id', true)::uuid)
    with check (id = current_setting('app.workspace_id', true)::uuid);

create policy workspaces_runtime_delete on platform.workspaces
    for delete to knowledge_platform_runtime
    using (id = current_setting('app.workspace_id', true)::uuid);

create policy assistants_runtime_select on platform.assistants
    for select to knowledge_platform_runtime
    using (workspace_id = current_setting('app.workspace_id', true)::uuid);

create policy assistants_runtime_insert on platform.assistants
    for insert to knowledge_platform_runtime
    with check (workspace_id = current_setting('app.workspace_id', true)::uuid);

create policy assistants_runtime_update on platform.assistants
    for update to knowledge_platform_runtime
    using (workspace_id = current_setting('app.workspace_id', true)::uuid)
    with check (workspace_id = current_setting('app.workspace_id', true)::uuid);

create policy assistants_runtime_delete on platform.assistants
    for delete to knowledge_platform_runtime
    using (workspace_id = current_setting('app.workspace_id', true)::uuid);

grant select, insert on table platform.workspaces
    to knowledge_platform_runtime;
grant select, insert on table platform.assistants
    to knowledge_platform_runtime;
