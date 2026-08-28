# Stage 0 — Repository Foundation Baseline

Version: 1.0
Status: ACCEPTED
Stage: 0 — Repository Foundation
Project: Configurable Knowledge Assistant Platform

## 1. Purpose

This document records the reproducible repository, tooling, architecture, and continuous
integration baseline established during Stage 0. It is an engineering baseline, not an
authorization to begin domain implementation.

## 2. Scope completed

Stage 0 established the Git-trackable repository skeleton, Python project metadata and lock,
workstation quality tooling, architecture boundary contract, GitHub origin, and GitHub Actions
quality workflow. The foundation is structurally valid, locally reproducible, remotely backed up,
and CI-validated.

## 3. Repository structure

The source tree is a module-first modular monolith using Ports and Adapters. The accepted roots
under `src/knowledge_platform` are `modules`, `infrastructure`, `delivery`, `config`, and
`bootstrap`. Module packages may contain `domain`, `application`, and `ports` boundaries where
present in the Stage 0 skeleton.

The test structure provides unit, application, contract, integration, security, evaluation, and
end-to-end suites. Architecture decisions, baseline records, evaluation suites, and Supabase
migration locations are represented by tracked directories.

## 4. Python and dependency baseline

- Workstation Python baseline: 3.13.15
- Project Python constraint: `>=3.13,<3.14`
- uv baseline: 0.12.6
- Dependency authority: `pyproject.toml` synchronized with `uv.lock`
- Locked dependency graph: 97 packages at baseline validation

The declared and locked runtime dependency set covers the API, configuration, persistence,
document, embedding, and HTTP capabilities planned for subsequent implementation stages. The
locked major versions include FastAPI 0.141.1, Pydantic 2.13.4, Pydantic Settings 2.15.0,
SQLAlchemy 2.0.52, Psycopg 3.3.4, pgvector 0.5.0, PyPDF 6.16.2, python-docx 1.2.0,
sentence-transformers 6.0.0, torch 2.13.0, and HTTPX 0.28.1.

Stage 0 local workstation development deliberately uses the selected workstation-wide Python 3.13
interpreter and does not use a project `.venv`. This records the current project decision and is not
a universal Python recommendation.

## 5. Quality tooling

The locked development toolchain includes pytest 9.1.1, pytest-cov 7.1.0, pytest-asyncio 1.4.0,
Hypothesis 6.165.10, Ruff 0.16.5, and mypy 2.3.1. The final Stage 0 validation produced:

- `uv lock --check`: passed
- Ruff over `src` and `tests`: passed
- strict mypy over `src` and the architecture contract: passed across 35 files
- pytest: 6 tests collected and 6 passed

## 6. Architecture boundary enforcement

The contract at `tests/contract/test_architecture_boundaries.py` statically scans imports with the
Python AST. It prevents domain, application, and ports code from importing infrastructure or
delivery and prevents accepted implementation frameworks from crossing into protected core layers.
Synthetic cases verify allowed inward dependencies, forbidden absolute imports, implementation
library violations, and structurally clear relative-import resolution. The actual repository scan
passes.

## 7. Git / GitHub baseline

- Branch: `main`
- Private origin: `https://github.com/abdulmajid-alhdad/configurable-knowledge-assistant-platform.git`
- Stage 0 pre-closure HEAD: `a396ff148815f49c4c33c7aaaf64d85095e42990`
- Local `main` tracks `origin/main`
- Local and remote pre-closure HEAD values were verified equal

## 8. Hosted CI evidence

The GitHub Actions workflow is named `Quality` and validates Python and uv setup, lock integrity,
the locked development toolchain, Ruff, strict mypy, pytest, and final repository integrity.

During C0-06, hosted execution was manually verified in the GitHub UI for commit `a396ff1`. The run
was triggered by a push to `main`; the `Quality` workflow and quality job completed successfully in
19 seconds. The hosted run ID was `33128353544`. This evidence was manually observed in the GitHub
UI during project-control review and was not independently queried by Codex.

## 9. Security / repository hygiene

No real `.env`, secret value, project virtual environment, Python cache, quality-tool cache, or
coverage output is tracked. `.env.example` contains only empty secret-capable fields and safe example
defaults. The repository ignore rules cover the generated caches observed during Stage 0. The CI job
has read-only repository permissions and does not require secrets or external model calls.

## 10. Deferred infrastructure

- Docker: DEFERRED
- Supabase CLI: DEFERRED
- GitHub CLI: NOT REQUIRED

Docker and Supabase CLI are not needed for the repository and domain foundation. They will be
required before work that depends on Supabase Local or persistence integration. Their absence is an
intentional sequencing decision, not a Stage 0 failure or technical debt. The existing Git remote and
manually verified hosted CI evidence make GitHub CLI unnecessary for this baseline.

## 11. Stage 0 exit criteria

The accepted baseline satisfies the Stage 0 structural, reproducibility, quality, architecture,
Git, remote-backup, hosted-CI, secret-hygiene, and no-project-venv criteria.

At final acceptance review, the only intended working-tree change is this baseline document,
pending its Stage 0 closure commit and push.

## 12. Stage 1 authorization dependency

The next planned stage is **Stage 1 — Core Contracts & Domain**. Stage 1 has not started and requires
explicit authorization after this Stage 0 baseline is reviewed and accepted.
