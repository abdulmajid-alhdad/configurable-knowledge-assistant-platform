# C2-05  KnowledgeSource Lifecycle Persistence

Version: 1.0
Status: ACCEPTED
Stage: 2  Platform Foundation & Core Slices

## 1. Purpose

Persist the workspace-owned KnowledgeSource aggregate while preserving its accepted lifecycle, typed identity, workspace authorization, and fail-closed RLS boundaries.

## 2. Authoritative KnowledgeSource Domain contract

Domain fields are `id: KnowledgeSourceId`, `workspace_id: WorkspaceId`, `name: str`, `kind: KnowledgeSourceKind`, and `lifecycle: KnowledgeSourceLifecycle`. `KnowledgeSource` is immutable and required text is normalized and validated.

KnowledgeSourceKind enum members are `DOCUMENT` and `STRUCTURED`; persisted values are `document` and `structured`.

KnowledgeSourceLifecycle enum member names are `REGISTERED`, `PREPARING`, `READY`, `DISABLED`, `FAILED`, `REMOVING`, and `REMOVED`. Persisted Domain StrEnum values are `registered`, `preparing`, `ready`, `disabled`, `failed`, `removing`, and `removed`.

The authoritative transition graph remains in the KnowledgeSource Domain. Infrastructure does not duplicate that graph. Only READY is retrieval eligible.

## 3. Table design

`platform.knowledge_sources` uses a KnowledgeSourceId UUID primary key, a non-null WorkspaceId foreign key to `platform.workspaces`, required name, kind, and lifecycle columns. No speculative ingestion or processing fields are persisted.

## 4. Lifecycle-state persistence

The database CHECK protects only the seven-state vocabulary. Lifecycle writes use `save_transition(previous, transitioned, workspace_id)`. Both aggregates must have the same KnowledgeSourceId, WorkspaceId, name, and kind; the transitioned lifecycle must be a valid Domain successor. The optimistic UPDATE requires the expected previous lifecycle and changes lifecycle only. Stale or zero-row updates fail explicitly. Generic `save(...)` and arbitrary state mutation are absent.

## 5. Workspace RLS

SELECT, INSERT, UPDATE, and DELETE policies use the transaction-local `app.workspace_id` context. RLS is enabled and forced; missing context does not match rows and malformed context fails closed. UPDATE uses both `USING` and `WITH CHECK` to prevent workspace movement.

## 6. Runtime privileges

`knowledge_platform_runtime` receives SELECT, INSERT, and UPDATE only. No DELETE grant exists. No broad grants or grants to public, anon, or authenticated are used.

## 7. ORM mapping

`KnowledgeSourceRecord` is a typed SQLAlchemy mapping outside Domain in the explicit `platform` schema. Migrations remain authoritative and no `metadata.create_all()` is used.

## 8. Persistence payloads/configuration

KnowledgeSource has no accepted configuration value object; no credentials or provider configuration are introduced.

## 9. Repository behavior

`KnowledgeSourceRepository` supports `add`, workspace-scoped `get`, and `save_transition(previous, transitioned, workspace_id)` only. It does not mutate kind, does not provide physical delete, and does not commit, rollback, close sessions, or create transactions.

## 10. Lifecycle transition integrity

The Domain transition graph is the sole semantic authority. Persistence requires previous and transitioned aggregates, validates identity/workspace/name/kind invariants, validates the candidate successor through the Domain, and applies an expected-previous-state optimistic update. `REMOVED` remains persisted; no repository operation mutates kind. READY-only retrieval eligibility remains Domain-owned.

## 11. Retrieval eligibility boundary

READY-only retrieval eligibility remains Domain-owned. C2-05 does not implement retrieval or duplicate eligibility queries.

## 12. Physical deletion boundary

There is no physical delete repository operation and no DELETE runtime privilege. REMOVED remains a persisted lifecycle state for audit and referential integrity.

## 13. Security invariants

Workspace identity must originate from trusted application authorization context. Prompt, history, retrieved content, and model output cannot grant workspace access or lifecycle authority. PostgreSQL RLS is defense in depth.

## 14. Test evidence

Static migration, ORM, mapper, repository, lifecycle transition, invalid-kind/lifecycle, lower-case representation, stale-update, and Domain-isolation tests are performed without a live database.

## 15. Static vs live validation

Static migration validation: PERFORMED. ORM/mapping validation: PERFORMED. Repository unit validation: PERFORMED. Lifecycle transition persistence validation: PERFORMED. Live PostgreSQL migration: NOT PERFORMED. Live PostgreSQL CHECK behavior: NOT PERFORMED. Live PostgreSQL FK behavior: NOT PERFORMED. Live PostgreSQL RLS behavior: NOT PERFORMED. Live concurrency behavior: NOT PERFORMED.

## 16. Explicit non-goals

No ingestion, parsing, chunking, embeddings, vectors, retrieval, structured database adapters, credential resolution, workers, APIs, or live Supabase connectivity are included.

## 17. Next task

C2-06  Conversation & Messages Persistence.

C2-05 Baseline Version: 1.0
C2-05 Status: ACCEPTED
Acceptance Date: 2026-08-29
Accepted By: Project Control
Domain Mapping: PASS
KnowledgeSourceKind Persistence: PASS
Lifecycle Value Persistence: PASS
Transition Authority: PASS
Transition Graph Preservation: PASS
Optimistic Previous-State Guard: PASS
Workspace Authorization: PASS
RLS Contract: PASS
Runtime Least Privilege: PASS
Physical Delete Boundary: PASS
Retrieval Eligibility Boundary: PASS
Runtime Grants: SELECT, INSERT, UPDATE
DELETE Grant: NO
Live PostgreSQL Migration: NOT PERFORMED
Live RLS Validation: NOT PERFORMED
Live Concurrency Behavior: NOT PERFORMED
Dependency Changes: NO
Next Task: C2-06  Conversation & Messages Persistence

Quality evidence:

- Targeted C2-05 tests: 29 passed
- Full pytest: 168 passed
- Ruff: PASS
- mypy: PASS — 65 source files
- Architecture contract: 6 passed
- git diff --check: PASS
- Dependencies: UNCHANGED
- pyproject.toml: UNCHANGED
- uv.lock: UNCHANGED
- Final uv lock rerun: BLOCKED by known workstation cache ACL (`C:\Users\TOP TECH\AppData\Local\uv\cache\sdists-v9\.git`: Access is denied). This is not a C2-05 dependency defect because dependency files are unchanged.
