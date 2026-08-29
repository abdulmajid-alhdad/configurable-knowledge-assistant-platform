# Stage 1  Core Contracts & Domain Baseline

Version: 1.0
Status: ACCEPTED
Stage: 1  Core Contracts & Domain
Project: Configurable Knowledge Assistant Platform

## 1. Purpose

This document records the accepted Stage 1 framework-independent domain contracts and the evidence used for final review. It is the accepted Stage 1 baseline.

## 2. Stage 1 Scope

Stage 1 establishes typed identifiers, aggregate roots, source lifecycle and access rules, conversation contracts, retrieval/evidence/grounding contracts, policy and credential boundaries, and evaluation contracts. It contains no persistence or infrastructure implementation.

## 3. Completion Status

C1-01 through C1-08 are CLOSED / ACCEPTED. Stage 1  Core Contracts & Domain is COMPLETE / ACCEPTED. The final baseline commit was pushed successfully. Final Hosted Quality passed.

## 4. Accepted Commit Lineage

- `afca6b12fd790034944772915f0818e06de3e932` — `feat: add typed domain identifiers`
- `67f34fae0591fd58eec3371957b19b18d7311571` — `feat: add workspace and assistant domain`
- `f2126d6f9ea37ffb839851f719e4e4d296738bc4` — `feat: add knowledge source lifecycle and access`
- `00b48d50b73e08e3d3ff7f98d6631ec1979f177c` — `feat: add conversation domain contracts`
- `330067f0bd9a1d6b927a41a2d510a71763a66953` — `feat: add retrieval evidence and grounding contracts`
- `b083a3fbbd7e5531195db03a6ae08ba7d80909e9` — `feat: add policy credential and egress contracts`
- `552dbd36758ddb38806e096fdd3b30d3b08cf6fa` — `feat: add evaluation domain contracts`

## 5. Domain Identifier Foundation

UUID-backed, frozen, slotted value objects provide runtime-distinct `WorkspaceId`, `AssistantId`, `KnowledgeSourceId`, `ConversationId`, and `EvaluationRunId` types. Each supports `new()` and stable string conversion.

## 6. Workspace & Assistant Domain

`Workspace` is a logical ownership boundary with `WorkspaceId` and validated name; it does not contain child object graphs. `Assistant` belongs immutably to one `WorkspaceId`, owns validated `ModelConfiguration` and explicit default `RetrievalConfiguration`, and supports validated immutable reconfiguration while preserving identity and workspace.

## 7. Knowledge Source Lifecycle & Access

`KnowledgeSource` is workspace-owned and immutable, with exact kinds `DOCUMENT` and `STRUCTURED`. Administrative lifecycle is `REGISTERED`, `PREPARING`, `READY`, `DISABLED`, `FAILED`, `REMOVING`, and `REMOVED`; only `READY` is retrieval eligible. `KnowledgeAccessScope` grants explicit source IDs for one assistant; empty scope means deny-all and cross-workspace sources are rejected. Access does not infer lifecycle readiness.

## 8. Conversation Domain

Immutable `Conversation`, `Message`, and `MessageRole` contracts bind conversations to a workspace and assistant. Messages are ordered, typed, normalized, and non-blank; append and context operations return validated replacements.

## 9. Retrieval Orchestration

`RetrievalRequest`, `EligibleSources`, `RetrievalPlan`, `RetrievedContent`, and `RetrievalResult` are immutable typed contracts. Plans cannot include sources outside policy-derived eligibility, and results cannot contain content from unplanned sources.

## 10. Evidence & Grounding

`Evidence` preserves `KnowledgeSourceId`, content, and opaque domain-neutral provenance. `GroundedAnswer` requires non-blank text and at least one evidence item. Zero evidence produces explicit `InsufficientEvidence`; outcomes also distinguish `PolicyDenied` and `TechnicalFailure`.

## 11. Policy / Credential / Data Egress

`CredentialReference` stores only a normalized logical name. `CredentialResolverPort` is a framework-free port; secret material is not part of domain structures. `DataEgressPolicy` uses trusted typed state and defaults private external processing to `DENY`; local processing is allowed. Prompt, history, retrieved content, and model output cannot grant privileges.

## 12. Evaluation Domain

Exact `EvaluationType` values are `DETERMINISTIC`, `REFERENCE_BASED`, and `MODEL_ASSISTED`. Immutable `EvaluationCase` and `EvaluationSuite` enforce normalized keys, non-empty suites, and unique case keys. `EvaluationRun` uses `EvaluationRunId`, exact lifecycle `CREATED`, `RUNNING`, `COMPLETED`, `FAILED`, rejects duplicate/unknown cases, and completes only when every suite case has exactly one result. `MODEL_ASSISTED` is classification only.

## 13. Cross-Cutting Invariants

- Aggregate identities are typed UUID values.
- Adopted domain values are immutable and slotted.
- Workspace isolation is explicit and fail-closed.
- Authorization scope is distinct from source lifecycle.
- Only `READY` sources are retrieval eligible.
- Retrieved content is untrusted input.
- Grounding cannot claim support without evidence.
- Insufficient evidence is explicit, never fabricated.
- Credential references are logical names, never secrets.
- Private external egress defaults to deny.
- Evaluation runs require exact suite-case coverage.

## 14. Security Boundaries

The LLM never receives database secrets. Prompt/history/retrieved/model output are untrusted and cannot authorize sensitive actions. Private-data egress follows this accepted matrix:

- LOCAL + non-private -> ALLOW
- LOCAL + private -> ALLOW
- EXTERNAL + non-private -> ALLOW
- EXTERNAL + private -> DENY by default
- EXTERNAL + private -> ALLOW only when explicitly permitted by trusted policy configuration

Prompt/history/retrieved content/model output cannot alter policy, grant privileges, or resolve credentials. Raw LLM-generated SQL execution is prohibited by the accepted architecture. Future structured retrieval must use:

`typed StructuredQueryPlan` -> domain/policy validation -> controlled compiler -> parameterized read-only query execution

Model output is never executable authority.

## 15. Architecture Boundaries

The repository remains a Modular Monolith using Ports and Adapters and module-first organization. Domain code has no FastAPI, SQLAlchemy, Psycopg, pgvector, parser, provider SDK, or persistence dependency. No generic God Aggregate or arbitrary `Any` configuration bag was introduced.

## 16. Explicit Non-Goals / Deferred Concerns

Persistence, Supabase, SQLAlchemy, migrations, HTTP adapters, provider SDKs, document ingestion, embeddings, model execution, API routes, and infrastructure are deferred. Lifecycle readiness beyond administrative `READY` semantics is deferred.

## 17. Remote Model Implementation Constraint

Decision `DEC-IMPL-REMOTE-MODEL-001`: no local LLM weights or embedding-model weights are included or required. No sentence-transformers, Torch, or Transformers runtime is required. Generation and embeddings are provider-neutral outbound-port concerns; local execution remains an extension point only and is not claimed as tested.

## 18. JSON Document Decision

Decision `DEC-IMPL-DOCUMENT-JSON-001`: JSON is an MVP document/semi-structured source type for a later stage, parsed structurally with stdlib `json`; path-level provenance may use JSON Pointer where practical. Malformed JSON will map to source failure, and arbitrary JSON expression execution is excluded.

## 19. Roadmap Consolidation Mapping

Decision `DEC-IMPL-ROADMAP-CONSOLIDATION-001` preserves traceability to the detailed roadmap:

1. Stage 0 Repository Foundation
2. Stage 1 Core Contracts & Domain
3. Stage 2 Platform Foundation & Core Slices
4. Stage 3 Document RAG Vertical Slice
5. Stage 4 Safe Structured Retrieval
6. Stage 5 Evaluation & Yemen Reference
7. Stage 6 Hardening & Portfolio Release

## 20. Quality Evidence

At C1-08 verification:

- Full pytest: `104 passed`
- Ruff: PASS
- mypy: PASS, 58 source files
- architecture contract: `6 passed`
- `uv lock --check --offline`: PASS, 97 packages resolved
- `git diff --check`: PASS
- `pyproject.toml` and `uv.lock`: unchanged
- no project virtual environment detected

Verified hosted Quality evidence:

- C1-02 — Quality #4 — PASS
- C1-03 — Quality #5 — PASS
- C1-04 — Quality #6 — PASS
- C1-05 — Quality #7 — PASS
- C1-06 — Quality #8 — PASS
- C1-07 — Quality #9 — PASS
- C1-08 — Quality #10 — PASS

Final accepted baseline commit: `dda516786a77a3058022ece184e3b6d5f768f8b4`.

## 21. Known Development Artifacts / Exclusions

The following known untracked C1-03 scratch artifacts remain outside project history: `openrouter_glm53_bridge.mjs` and `c1-03-*.txt`. They are not product code and are excluded from all Stage 1 commits. No scratch artifact is staged or tracked.

## 22. Stage 2 Entry Conditions

Stage 2 may begin only after:

1. C1-08 final quality evidence passes.
2. Project Control reviews this baseline.
3. Status changes from `PROPOSED` to `ACCEPTED`.
4. The accepted baseline is committed and pushed.
5. Hosted Quality passes for the baseline commit.

Stage 2 starts with dependency correction / `C2-00` before broad installation work. `C2-00` is not implemented here.

All Stage 2 entry conditions are now SATISFIED.

Stage 2  Platform Foundation & Core Slices: AUTHORIZED

Next task: C2-00  Dependency Correction & Runtime Baseline

## 23. Baseline Acceptance Record

Baseline Version: 1.0
Baseline Status: ACCEPTED
Acceptance Date: 2026-08-29
Accepted By: Project Control
C1-08 Final Quality Gate: ACCEPTED
Final Baseline Commit: dda516786a77a3058022ece184e3b6d5f768f8b4
Hosted Quality: Quality #10  PASS
Stage 1 Closure: COMPLETE / ACCEPTED
Stage 2: AUTHORIZED
Next Task: C2-00  Dependency Correction & Runtime Baseline
