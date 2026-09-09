-- Stage 6I-2: durable, provider-neutral assistant outcomes and evidence snapshots.
alter table platform.conversations
    add column created_at timestamptz null;

-- Historical conversations did not persist creation time. Keep that absence
-- explicit instead of assigning the migration timestamp as fabricated history.
alter table platform.conversations
    alter column created_at set default now();

alter table platform.messages
    add column outcome text null,
    add constraint messages_outcome_vocabulary check (
        outcome is null or outcome in (
            'grounded', 'insufficient_evidence', 'policy_denied', 'technical_failure'
        )
    ),
    add constraint messages_assistant_outcome_only check (
        outcome is null or role = 'assistant'
    );

create table platform.message_evidence (
    conversation_id uuid not null,
    message_sequence integer not null,
    ordinal integer not null,
    source_id uuid not null references platform.knowledge_sources (id),
    content text not null,
    provenance_locator text not null,
    primary key (conversation_id, message_sequence, ordinal),
    foreign key (conversation_id, message_sequence)
        references platform.messages (conversation_id, sequence),
    constraint message_evidence_ordinal_positive check (ordinal > 0),
    constraint message_evidence_content_nonblank check (btrim(content) <> ''),
    constraint message_evidence_provenance_nonblank
        check (btrim(provenance_locator) <> '')
);

alter table platform.message_evidence enable row level security;
alter table platform.message_evidence force row level security;

create policy message_evidence_runtime_select on platform.message_evidence
    for select to knowledge_platform_runtime
    using (conversation_id in (
        select id from platform.conversations
        where workspace_id = current_setting('app.workspace_id', true)::uuid
    ));

create policy message_evidence_runtime_insert on platform.message_evidence
    for insert to knowledge_platform_runtime
    with check (
        conversation_id in (
            select id from platform.conversations
            where workspace_id = current_setting('app.workspace_id', true)::uuid
        )
        and source_id in (
            select id from platform.knowledge_sources
            where workspace_id = current_setting('app.workspace_id', true)::uuid
        )
    );

grant select, insert on table platform.message_evidence
    to knowledge_platform_runtime;
