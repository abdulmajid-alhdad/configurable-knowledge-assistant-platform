create extension if not exists vector;
create table retrieval.document_representations (
    id uuid primary key,
    workspace_id uuid not null references platform.workspaces(id),
    source_id uuid not null references platform.knowledge_sources(id),
    version integer not null check (version > 0),
    embedding_profile text not null,
    dimensions integer not null check (dimensions > 0),
    state text not null check (state in ('BUILDING', 'ACTIVE', 'RETIRED')),
    unique (source_id, version)
);
create unique index one_active_representation_per_source on retrieval.document_representations(source_id) where state = 'ACTIVE';
create table retrieval.document_chunks (
    representation_id uuid not null references retrieval.document_representations(id),
    sequence integer not null check (sequence >= 0),
    content text not null check (btrim(content) <> ''),
    provenance_locator text not null,
    embedding vector not null,
    primary key (representation_id, sequence)
);
alter table retrieval.document_representations enable row level security;
alter table retrieval.document_representations force row level security;
alter table retrieval.document_chunks enable row level security;
alter table retrieval.document_chunks force row level security;
create policy representations_workspace on retrieval.document_representations for all to knowledge_platform_runtime using (workspace_id = current_setting('app.workspace_id', true)::uuid) with check (workspace_id = current_setting('app.workspace_id', true)::uuid);
create policy chunks_workspace on retrieval.document_chunks for all to knowledge_platform_runtime using (representation_id in (select id from retrieval.document_representations where workspace_id = current_setting('app.workspace_id', true)::uuid)) with check (representation_id in (select id from retrieval.document_representations where workspace_id = current_setting('app.workspace_id', true)::uuid));
grant select, insert, update on table retrieval.document_representations to knowledge_platform_runtime;
grant select, insert on table retrieval.document_chunks to knowledge_platform_runtime;
