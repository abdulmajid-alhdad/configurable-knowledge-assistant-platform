# C2-04  Workspace & Assistant Persistence Slice

Version: 1.0
Status: ACCEPTED
Stage: 2  Platform Foundation & Core Slices
Project: Configurable Knowledge Assistant Platform

## 1. Purpose

Provide the first platform persistence slice for Workspace and Assistant with PostgreSQL constraints, SQLAlchemy mappings, workspace isolation, and explicit adapters.

## 2. Domain-to-persistence mapping

Accepted immutable Domain objects map to `platform.workspaces` and `platform.assistants` records. Typed UUID identifiers and Domain validation remain authoritative during hydration.

## 3. Table design

The migration creates only `platform.workspaces` and `platform.assistants`. Assistant rows contain a non-null `workspace_id`, `model_configuration JSONB NOT NULL`, and `retrieval_configuration JSONB NOT NULL`. No timestamps or speculative metadata are added.

## 4. Foreign keys/constraints

`platform.assistants.workspace_id` references `platform.workspaces.id`. Primary keys and non-null constraints match the current Domain requirements. Required-text checks are `workspaces_name_nonblank`, `assistants_name_nonblank`, `assistants_instructions_nonblank`, and `assistants_language_nonblank`. `description` remains nullable.

## 5. Workspace transaction context

`set_workspace_context(session, workspace_id)` and `workspace_session_scope(factory, workspace_id)` provide the transaction-scoped context boundary. The latter opens one SQLAlchemy transaction, sets `app.workspace_id` on the same Session, yields it, and lets SQLAlchemy commit/rollback/close. The setter uses parameterized SQL and `set_config(..., true)`.

## 6. Workspace RLS

Workspace policies scope every operation to `id = current_setting('app.workspace_id', true)::uuid`. Missing context yields no match; malformed context fails rather than falling back to unrestricted access.

## 7. Assistant RLS

Assistant SELECT, INSERT, UPDATE, and DELETE policies scope `workspace_id` to the transaction context. UPDATE uses both `USING` and `WITH CHECK`, preventing workspace movement.

## 8. Runtime privileges

`knowledge_platform_runtime` receives only SELECT and INSERT on these two tables. RLS UPDATE/DELETE policies remain defensive, but the runtime role has no SQL UPDATE/DELETE grants. It does not own the tables, receive `GRANT ALL`, or receive public/anon/authenticated privileges.

## 9. ORM mappings

SQLAlchemy 2.x typed mappings live in infrastructure under the explicit `platform` schema. Configuration uses validated Pydantic v2 `ModelConfigurationPayload` and `RetrievalConfigurationPayload` objects with extra fields forbidden; no secret or credential fields are persisted. No ORM types enter Domain and no `metadata.create_all()` is used.

## 10. Persistence adapters

`WorkspaceRepository` supports `add` and `get` by WorkspaceId; row identity is the workspace identity and RLS is defense in depth. `AssistantRepository.add` requires trusted WorkspaceId and rejects mismatch; `get` filters by AssistantId and WorkspaceId. Repositories do not commit, rollback, close sessions, or create transactions. No generic repository framework is introduced.

## 11. Security invariants

Workspace identity comes only from trusted application authorization context. Prompt, history, retrieved content, and model output cannot grant access. RLS is defense in depth and runtime role privileges are least privilege.

## 12. Test evidence

Static/unit tests directly verify JSONB mappings, validated payloads, mapper roundtrips, repository behavior, Assistant workspace mismatch and dual predicate, transaction-local context, `workspace_session_scope`, policy-scoped RLS artifacts, and exact SELECT/INSERT grants without requiring PostgreSQL.

## 13. Static vs live PostgreSQL validation boundary

Static migration validation: PERFORMED. ORM/mapping validation: PERFORMED. Repository unit validation: PERFORMED. Transaction-context unit validation: PERFORMED. Static tests do not prove live PostgreSQL RLS behavior. Live PostgreSQL migration: NOT PERFORMED. Live PostgreSQL FK validation: NOT PERFORMED. Live PostgreSQL RLS behavior: NOT PERFORMED.

## 14. Explicit non-goals

No KnowledgeSource, Conversation, Evaluation, document/vector persistence, API routes, Data API, service-role usage, live provisioning, or generic persistence framework is included.

## 15. Next task

C2-05  KnowledgeSource Lifecycle Persistence.

C2-04 Baseline Version: 1.0
C2-04 Status: ACCEPTED
Acceptance Date: 2026-08-29
Accepted By: Project Control
Workspace Persistence Mapping: PASS
Assistant Persistence Mapping: PASS
JSONB Configuration Persistence: PASS
Validated Configuration Payloads: PASS
Database Constraints: PASS
Workspace RLS Contract: PASS
Assistant RLS Contract: PASS
Runtime Least Privilege: PASS
Workspace Transaction Context: PASS
Repository Workspace Validation: PASS
Domain Framework Isolation: PASS
Live PostgreSQL Migration: NOT PERFORMED
Live RLS Validation: NOT PERFORMED
Dependency Changes: NO
Next Task: C2-05  KnowledgeSource Lifecycle Persistence
