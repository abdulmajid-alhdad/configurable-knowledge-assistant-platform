# Stage 3  Document RAG Vertical Slice

Version: 1.0
Status: ACCEPTED
Acceptance Date: 2026-08-30
Accepted By: Project Control
Project: Configurable Knowledge Assistant Platform

## Purpose

Stage 3 establishes a provider-neutral document RAG path: document parsing,
normalization, deterministic chunking, remote embeddings, versioned retrieval
representations, workspace/source-scoped vector search, evidence, grounding,
egress policy, and remote generation.

## Implementation boundary

TXT, Markdown, JSON, DOCX, and text-bearing PDF parsers are explicit adapters.
Malformed JSON and empty/scanned content fail explicitly; OCR is deferred.
Normalization and chunking are deterministic and preserve provenance.

Representations and chunks live in the retrieval schema. BUILDING, ACTIVE, and
RETIRED states are persisted; at most one ACTIVE representation exists per
source and activation occurs only after complete chunk/embedding persistence.
The PostgreSQL/pgvector adapter requires trusted workspace and explicit source
ids, filters ACTIVE representations, orders by vector similarity, bounds the
limit, and returns no results for an empty source set.

KnowledgeSource lifecycle transitions remain Domain-owned: preparation precedes
processing, READY follows successful activation, and failures transition to
FAILED. Disabled, failed, removing, and removed sources are not eligible for
new retrieval. Conversation integration uses the existing append-only
repositories and transaction scope; history is not authorization.

EmbeddingGatewayPort and ModelPort are provider-neutral remote HTTP boundaries.
DataEgressPolicy is evaluated before model calls; denied egress performs zero
provider calls and credentials are never placed in prompts or payloads.

## Security and architecture

WorkspaceId is trusted application input and app.workspace_id remains
transaction-local. RLS and application workspace/source filtering are defense
in depth. No local model runtime or forbidden model dependency is used. Domain
modules remain free of infrastructure imports. No Supabase Data API, service
role shortcut, generic repository, or metadata.create_all() is introduced.

## Validation evidence

Static migration/query validation, ORM/mapping validation, repository and
orchestration unit validation are performed. Direct DOCX/PDF adapter tests are
included where the corresponding runtime libraries are available.

Live PostgreSQL migration: NOT PERFORMED
Live pgvector behavior: NOT PERFORMED
Live RLS behavior: NOT PERFORMED

## Explicit non-goals

Structured retrieval, SQL planning/execution, ingestion workers, OCR, vector
production operations, embeddings/generation through local models, and broad
UI/API work are deferred.

## Next stage

Stage 4  Safe Structured Retrieval

## Acceptance evidence

Targeted Stage 3 tests: 7 passed
Full pytest: 187 passed
Ruff: PASS
mypy: PASS 75 source files
Architecture contract: 6 passed
git diff --check: PASS
uv lock: BLOCKED by known workstation cache ACL
pyproject.toml: UNCHANGED
uv.lock: UNCHANGED
Dependencies changed: NO
Forbidden local-model dependencies: ABSENT

Parser, chunking, lifecycle, conversation, pgvector query-contract, and
deterministic E2E validation were performed. DOCX and PDF direct fixture
validation was performed. Remote embedding validation used test doubles/mocks.

The accepted runtime path is: question -> trusted Workspace/Assistant context
-> eligible READY sources -> remote query embedding -> workspace/source/ACTIVE
vector search -> RetrievalResult -> Evidence -> Grounding -> Data Egress
decision -> remote ModelPort -> AssistantOutcome -> append-only conversation.
Supported outcomes are GroundedAnswer, InsufficientEvidence, PolicyDenied, and
TechnicalFailure. Conversation history is not authorization.

Live PostgreSQL migration: NOT PERFORMED
Live PostgreSQL pgvector execution: NOT PERFORMED
Live PostgreSQL RLS: NOT PERFORMED
