# C2-06  Conversation & Messages Persistence

Version: 1.0
Status: ACCEPTED
Stage: 2  Platform Foundation & Core Slices

## 1. Purpose

Persist the accepted Conversation aggregate and its immutable, ordered Messages in the private platform schema.

## 2. Authoritative Domain contract

Conversation contains `ConversationId`, `WorkspaceId`, `AssistantId`, and an ordered immutable `tuple[Message, ...]`. Message contains non-negative `sequence`, `MessageRole` (`user` or `assistant`), and normalized nonblank content. Conversation creation starts with no messages; `append_message` assigns the next sequence.

## 3. Conversation table

`platform.conversations` stores UUID `id`, non-null UUID `workspace_id`, and non-null UUID `assistant_id` with foreign keys to the accepted platform workspace and assistant tables.

## 4. Message table

`platform.messages` stores composite identity `(conversation_id, sequence)`, role, and content. Messages are append-only through the repository; no update or delete operation is implemented.

## 5. Ownership/FKs

Conversation is workspace-owned and assistant-linked through `workspace_id -> platform.workspaces.id` and `assistant_id -> platform.assistants.id`. Message ownership is relational through `conversation_id -> platform.conversations.id`; its RLS policy resolves the conversation workspace through a fail-closed workspace predicate.

## 6. Message ordering/integrity

Sequence is non-negative and unique per conversation through the composite primary key `(conversation_id, sequence)`. Role vocabulary is exactly `user | assistant`, content is nonblank, and persistence is append-only. Domain append behavior remains authoritative.

## 7. Workspace RLS

RLS is enabled and forced on both tables. Conversations use direct workspace predicates. Messages use a subquery through `platform.conversations` and the transaction-local `app.workspace_id`; missing context yields no match and malformed context fails.

## 8. Runtime privileges

The runtime role receives SELECT and INSERT only on both tables. UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, broad grants, and public/anon/authenticated grants are absent.

## 9. ORM mappings

`ConversationRecord` and `MessageRecord` are typed SQLAlchemy mappings in the explicit `platform` schema. No `metadata.create_all()` or Domain ORM coupling is used.

## 10. Domain/persistence mapping

Mappers preserve typed IDs, assistant/workspace ownership, message role/content, and sequence ordering. Hydration reconstructs Domain objects and validates enum/value invariants.

## 11. Repository behavior

`ConversationRepository` supports `add` and workspace-scoped `get` with ordered Message reconstruction. `MessageRepository` provides append-only `add` with workspace and sequence validation. No generic update/delete API exists. Repositories do not commit, rollback, close sessions, or own a transaction boundary.

## 12. Mutation/append boundary

Messages are immutable and append-only. No generic message update/delete API exists. Runtime SQL privileges reflect that boundary.

## 13. Security invariants

Workspace identity comes from trusted transaction-local application context and explicit WorkspaceId checks. Conversation text and model/retrieved content never grant authorization. RLS is defense in depth.

## 14. Test evidence

Static migration, ORM metadata, mapper roundtrip, repository workspace, ordering, privilege, and Domain-isolation validation are performed without a live database.

## 15. Static vs live validation

Static migration validation: PERFORMED. ORM/mapping validation: PERFORMED. Repository unit validation: PERFORMED. Conversation/message persistence unit validation: PERFORMED. Live PostgreSQL migration: NOT PERFORMED. Live PostgreSQL FK behavior: NOT PERFORMED. Live PostgreSQL RLS behavior: NOT PERFORMED.

## 16. Explicit non-goals

No KnowledgeSource changes, ingestion, parsing, retrieval, embeddings, vectors, structured execution, APIs, Supabase Data API, or live provisioning are included.

## 17. Next task

C2-07  Stage 2 Integration, Regression & Acceptance Baseline.

C2-06 Baseline Version: 1.0
C2-06 Status: ACCEPTED
Acceptance Date: 2026-08-29
Accepted By: Project Control
Conversation Persistence: PASS
Message Persistence: PASS
Workspace Ownership: PASS
Assistant Ownership: PASS
Message Ordering Integrity: PASS
Append-Only Boundary: PASS
RLS Contract: PASS
Runtime Least Privilege: PASS
Repository Workspace Validation: PASS
Domain Framework Isolation: PASS
Runtime Grants: Conversation = SELECT, INSERT; Message = SELECT, INSERT
UPDATE Grant: NO
DELETE Grant: NO
Live PostgreSQL Migration: NOT PERFORMED
Live RLS Validation: NOT PERFORMED
Dependency Changes: NO
Next Task: C2-07  Stage 2 Integration, Regression & Acceptance Baseline

Quality evidence:

- Targeted C2-06 tests: 5 passed
- Full pytest: 173 passed
- Ruff: PASS
- mypy: PASS — 65 source files
- Architecture contract: 6 passed
- git diff --check: PASS
- pyproject.toml: UNCHANGED
- uv.lock: UNCHANGED
