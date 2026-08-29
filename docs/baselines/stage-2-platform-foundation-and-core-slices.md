# Stage 2  Platform Foundation & Core Slices

Version: 1.0
Status: ACCEPTED
Project: Configurable Knowledge Assistant Platform

## 1. Stage purpose

Stage 2 establishes the platform runtime, private PostgreSQL schema/security foundation, and core Workspace, Assistant, KnowledgeSource, Conversation, and Message persistence slices.

## 2. Accepted task inventory

C2-00 Dependency Correction & Runtime Baseline; C2-01 Platform Database Configuration & SQLAlchemy Foundation; C2-02 Schema & Migration Foundation; C2-03 Runtime Role + Workspace Isolation Foundation; C2-04 Workspace & Assistant Persistence; C2-05 KnowledgeSource Lifecycle Persistence; C2-06 Conversation & Messages Persistence; C2-07 Stage 2 Integration, Regression & Acceptance Baseline.

## 3. Dependency/runtime baseline

Python 3.13, uv, `pyproject.toml`, and `uv.lock` are authoritative. The accepted remote-model constraint excludes local model weights/runtime and the removed local inference stack: sentence-transformers, torch, transformers, tokenizers, and safetensors. No project-local virtual environment is required.

## 4. Database configuration foundation

Pydantic Settings validates the platform PostgreSQL `postgresql+psycopg` DSN. SQLAlchemy 2.x with Psycopg provides engine, session factory, and transaction boundaries without implicit connections or ORM metadata creation.

## 5. Private schema foundation

Supabase SQL migrations are authoritative. Private schemas are `platform`, `retrieval`, and `evaluation`; no application tables were created until subsequent slices. Alembic is not used.

## 6. Runtime role/security boundary

`knowledge_platform_runtime` is a dedicated non-privileged role with fail-closed attribute, membership, ownership, and effective CREATE checks. It receives schema USAGE only and no broad public exposure.

## 7. Workspace transaction context

Trusted application authorization sets transaction-local `app.workspace_id` through `workspace_session_scope(...)` and parameterized `set_config(..., true)`. Prompt, history, retrieved data, and model output cannot set authorization context.

## 8. Workspace persistence

`platform.workspaces` stores UUID identity and validated nonblank name with workspace RLS and runtime SELECT/INSERT privileges.

## 9. Assistant persistence

`platform.assistants` is workspace-scoped and assistant-linked to Workspace. Configuration persists as validated JSONB payloads; runtime privileges are SELECT/INSERT.

## 10. KnowledgeSource lifecycle persistence

`platform.knowledge_sources` preserves typed identity, workspace ownership, `document|structured` kind, and lowercase lifecycle values. Domain owns the transition graph; `save_transition` uses an expected previous-state guard and lifecycle-only update. Runtime privileges are SELECT/INSERT/UPDATE; no physical delete exists.

## 11. Conversation persistence

`platform.conversations` stores ConversationId, WorkspaceId, and AssistantId with workspace/assistant foreign keys and workspace RLS. Runtime privileges are SELECT/INSERT.

## 12. Message persistence

`platform.messages` stores immutable role/content messages with composite `(conversation_id, sequence)` identity, sequence and vocabulary checks, relational workspace RLS, and append-only SELECT/INSERT privileges.

## 13. Complete table inventory

The Stage 2 platform tables are `workspaces`, `assistants`, `knowledge_sources`, `conversations`, and `messages`, all in schema `platform` with UUID identities except the message sequence component.

## 14. Complete FK graph

Assistants reference Workspaces. KnowledgeSources reference Workspaces. Conversations reference Workspaces and Assistants. Messages reference Conversations.

## 15. Complete runtime privilege matrix

| Table | Runtime privileges |
|---|---|
| `platform.workspaces` | SELECT, INSERT |
| `platform.assistants` | SELECT, INSERT |
| `platform.knowledge_sources` | SELECT, INSERT, UPDATE |
| `platform.conversations` | SELECT, INSERT |
| `platform.messages` | SELECT, INSERT |

DELETE, TRUNCATE, REFERENCES, TRIGGER, GRANT ALL, and default-privilege expansion are absent. No public, anon, or authenticated grants exist.

## 16. RLS/tenant-isolation model

All five tables enable and force RLS. Direct workspace tables use `workspace_id = current_setting('app.workspace_id', true)::uuid`; workspace rows use `id`; messages resolve workspace through conversations. RLS is defense in depth alongside application-layer WorkspaceId validation.

## 17. JSONB configuration boundary

Assistant `model_configuration` and `retrieval_configuration` remain JSONB and are validated by infrastructure payload models with forbidden extra fields and no credentials.

## 18. KnowledgeSource lifecycle authority

The Domain is the sole lifecycle authority. Infrastructure has no duplicate graph or generic state setter. READY-only retrieval eligibility remains Domain-owned.

## 19. Append-only message boundary

Messages are immutable and appended through explicit repository behavior. No runtime UPDATE/DELETE grants or generic mutation API exists.

## 20. Repository transaction ownership

Repositories perform explicit scoped operations but do not commit, rollback, close sessions, or create transactions. The application/session scope owns transaction lifecycle.

## 21. Security invariants

Workspace identity originates only from trusted application authorization. RLS is fail-closed defense in depth. Model output, prompts, history, and retrieved data are untrusted and cannot grant privileges or resolve credentials.

## 22. Architecture boundaries

Domain remains free of SQLAlchemy, Psycopg, and Pydantic Settings. No `metadata.create_all()`, GenericRepository, BaseRepository, UnitOfWork, Supabase Data API shortcut, raw LLM SQL execution, local model runtime, or service-role persistence shortcut exists.

## 23. Test/quality evidence

C2-07 integration contracts cover migration order, ORM table inventory, FK graph, RLS/force-RLS coverage, runtime privileges, JSONB/lifecycle/message regressions, and dependency exclusions. Full regression and architecture suites are run at the task gate.

## 24. Static vs live validation boundary

Static migration, ORM, mapping, repository, security, and regression validation is performed. Live Supabase/PostgreSQL migration, FK, RLS, and concurrency behavior are not performed by this baseline.

## 25. Known deferred operational validation

Live migration execution, live RLS behavior, live PostgreSQL concurrency semantics, and hosted deployment verification remain operational follow-up evidence.

## 26. Explicit Stage 2 non-goals

Stage 2 does not implement document RAG, parsing, chunking, embeddings, retrieval, structured retrieval, generation gateway, Yemen assistant, API routes, or live Supabase provisioning.

## 27. Stage 2 exit criteria

Repository foundation, dependency baseline, platform DB configuration, private schemas, runtime role, workspace isolation, all five persistence slices, static RLS/least privilege, ORM/Domain isolation, regression suite, and Hosted Quality readiness are PASS. Live PostgreSQL validation is DEFERRED and is not represented as PASS.

## 28. Next stage

Stage 3  Document RAG Vertical Slice.

Stage 2 Baseline Version: 1.0
Stage 2 Status: ACCEPTED
Acceptance Date: 2026-08-29
Accepted By: Project Control

Accepted tasks:

- C2-00
- C2-01
- C2-02
- C2-03
- C2-04
- C2-05
- C2-06
- C2-07

Live PostgreSQL migration: NOT PERFORMED
Live PostgreSQL FK behavior: NOT PERFORMED
Live PostgreSQL RLS behavior: NOT PERFORMED
Live PostgreSQL concurrency behavior: NOT PERFORMED
