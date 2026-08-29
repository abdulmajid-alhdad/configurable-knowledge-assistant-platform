# Stage 5  Evaluation & Yemen Reference

Version: 1.0
Status: ACCEPTED
Acceptance Date: 2026-08-30
Accepted By: Project Control
Project: Configurable Knowledge Assistant Platform

Stage 5 reuses the framework-independent Evaluation Domain, strict versioned
JSON suites, canonical SHA-256 hashing, and the existing EvaluationRun
lifecycle. Evaluation observes a normal application-facing execution port; it
does not call database, vector, credential, parser, or provider infrastructure
directly. Deterministic metrics include outcome, evidence, provenance, and
zero-violation security rates. REFERENCE_BASED is deterministic; MODEL_ASSISTED
remains classified but production judging is deferred.

Evaluation persistence uses `evaluation.evaluation_runs` and
`evaluation.evaluation_results` with RLS and least-privilege grants. Suite JSON
files remain the canonical definitions; diagnostics are minimized and contain
no secrets.

The Yemen History reference is ordinary Workspace, Assistant, KnowledgeSource,
KnowledgeAccessScope, retrieval, Evidence, Grounding, and Model contracts. Its
Arabic material is a clearly labeled DEMO / TEST REFERENCE FIXTURE, not an
authoritative corpus. There is no Yemen-specific Core branch.

Static migration/ORM/repository validation and deterministic suite/reference
tests are performed. Live PostgreSQL migration, RLS, and concurrency behavior
are NOT PERFORMED. Local full regression may remain blocked by the workstation
pgvector dependency environment.

Explicit non-goals: production model judges, corpus curation, ingestion,
retrieval redesign, and local model execution.

Next stage: Stage 6  Hardening & Portfolio Release

## Closure verification evidence

Persistence repository roundtrip contract: PERFORMED
Live PostgreSQL persistence: NOT PERFORMED
Yemen deterministic application execution: PERFORMED
Yemen suite: PERFORMED
Security suite: PERFORMED
External model calls: NOT REQUIRED

## Acceptance evidence

Evaluation Domain reused: PASS
Suite loader: PASS
Strict JSON validation: PASS
Stable suite hashing: PASS
Evaluation runner: PASS
Normal application path: PASS
Evaluation persistence: PASS
Evaluation ORM/mapping: PASS
Evaluation repository: PASS
Migration and RLS/static security: PASS
EvaluationRun lifecycle and incomplete-run protection: PASS
core.json execution: PASS
security.json execution: PASS
yemen_history.json execution: PASS
REFERENCE_BASED: PASS
MODEL_ASSISTED: CLASSIFICATION SUPPORTED / PRODUCTION JUDGE DEFERRED
unauthorized_execution_rate: 0.0
unauthorized_egress_rate: 0.0
credential_leak_rate: 0.0
Yemen History reference: PASS
Yemen special-case Core bypass: ABSENT
Arabic normal path: PASS
Yemen grounded execution: PASS
Yemen insufficient execution: PASS
Yemen provenance: PASS
Reference fixture: CLEARLY-LABELED DEMO / TEST FIXTURE
Secrets: ABSENT
Forbidden local-model dependencies: ABSENT
Raw LLM SQL: ABSENT

Targeted Stage 5 tests: 7 passed
Ruff: PASS
Architecture contract: 6 passed
Full local pytest: BLOCKED BY WORKSTATION ENVIRONMENT (pgvector unavailable)
Local mypy: BLOCKED BY WORKSTATION ENVIRONMENT (pgvector.sqlalchemy unavailable)
uv lock: BLOCKED BY KNOWN WORKSTATION CACHE ACL
pyproject.toml: UNCHANGED
uv.lock: UNCHANGED
Dependencies changed: NO
Live PostgreSQL/Supabase: NOT PERFORMED
