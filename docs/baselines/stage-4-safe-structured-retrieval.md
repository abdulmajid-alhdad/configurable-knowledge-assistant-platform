# Stage 4  Safe Structured Retrieval

Version: 1.0
Status: ACCEPTED
Acceptance Date: 2026-08-30
Accepted By: Project Control
Project: Configurable Knowledge Assistant Platform

Stage 4 defines a safe structured retrieval boundary for PostgreSQL and
SQLite external knowledge sources. Metadata is represented by platform-owned
contracts and never exposes driver objects. Credentials remain
CredentialReference values and are resolved only at adapter boundaries.

`StructuredQueryPlan` is a typed, non-executable request containing only an
approved relation, fields, filters, ordering, and bounded limit. Policy and
workspace/source/lifecycle validation produce a distinct
`ValidatedStructuredPlan`; executors cannot be called with the unvalidated
type. The SQLAlchemy Core compiler constructs SELECT statements with bound
parameters only. No raw SQL, multi-statement, mutation, DDL, or model-generated
SQL path exists.

SQLite executes through a read-only connection and PostgreSQL uses an explicit
external connection adapter. Results remain bounded and map to the existing
RetrievalResult/Evidence/Grounding contracts. Restricted relations/columns,
unknown sources, missing READY eligibility, and over-limit plans are denied
before execution. Prompt or database content cannot expand authority.

Static compiler and adapter contract validation is performed; SQLite real
integration is covered by tests. Live external PostgreSQL execution and live
Supabase validation are not performed. Stage 4 does not implement document
RAG changes, ingestion, embeddings, or local model execution.

Next stage: Stage 5  Evaluation & Yemen Reference

## Acceptance record

The trusted path is: natural-language question -> StructuredPlannerPort ->
untrusted StructuredQueryPlan -> schema and policy validation ->
ValidatedStructuredPlan -> SQLAlchemy Core parameterized SELECT -> read-only
structured adapter -> RetrievalResult -> Evidence -> Grounding ->
AssistantOutcome. Raw LLM SQL execution is prohibited; the plan has no raw SQL
field and executors do not accept unvalidated plans.

Restricted tables, restricted columns, and unknown relations are denied with
zero executor calls. Workspace/source validation, READY enforcement,
credential isolation, prompt-injection resistance, operational limits,
parameterization, and SELECT-only compilation pass. SQLite execution is read
only. Structured provenance and Evidence use the existing retrieval contracts;
insufficient evidence, policy denial, and technical database failure remain
distinct outcomes without silent model-knowledge fallback.

StructuredPlannerPort and deterministic fake-planner validation are implemented.
Production remote planner adapter is deferred; planner output remains
untrusted and must pass validation.

Targeted Stage 4 tests: 5 passed
SQLite real E2E: PASS
Property-based safety: PASS
Ruff: PASS
Architecture contract: 6 passed
Local full pytest: BLOCKED BY WORKSTATION ENVIRONMENT (pgvector missing)
Local exact mypy: BLOCKED BY WORKSTATION ENVIRONMENT (pgvector.sqlalchemy missing)
pyproject.toml: UNCHANGED
uv.lock: UNCHANGED
Dependencies changed: NO
Forbidden local-model dependencies: ABSENT
Live external PostgreSQL: NOT PERFORMED
