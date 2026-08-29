# C2-00  Dependency Correction & Runtime Baseline

Version: 1.0
Status: ACCEPTED
Stage: 2  Platform Foundation & Core Slices
Project: Configurable Knowledge Assistant Platform

## 1. Purpose

Correct the dependency graph before Stage 2 persistence or infrastructure work, preserving a reproducible Python and uv baseline without local model execution.

## 2. Superseding Decision

`DEC-IMPL-REMOTE-MODEL-001` supersedes the earlier local Sentence Transformers/BGE-M3 implementation target. The interview-ready implementation uses provider-neutral remote generation and embedding ports.

## 3. Python/runtime baseline

- Python: 3.13 (`>=3.13,<3.14`)
- Package management: `uv`
- Dependency declarations: `pyproject.toml` + `uv.lock`
- No project-local virtual environment is created or required.

## 4. Dependency partition

Runtime dependencies cover FastAPI, Uvicorn, Pydantic, settings, SQLAlchemy, Psycopg, pgvector, HTTP, and document capabilities. Development dependencies remain pytest, pytest-asyncio, pytest-cov, Hypothesis, Ruff, and mypy. Remote model and embedding adapters will use provider-neutral HTTP ports, preferably through existing `httpx`.

## 5. Removed local-model dependencies

Removed the direct `sentence-transformers` dependency from `pyproject.toml`. Lock regeneration removed the superseded local-inference stack, including `torch`, `transformers`, `tokenizers`, `safetensors`, CUDA/NVIDIA packages, and their supporting transitive graph. Packages such as NumPy, SciPy, scikit-learn, and Hugging Face support libraries were also pruned because no remaining accepted dependency currently requires them. They are not globally prohibited dependencies.

No local model/inference runtime stack remains in the current lock graph.

## 6. Remote model/embedding rule

No LLM or embedding weights are downloaded or executed locally. Ollama is not a current runtime requirement. Local model execution remains an architectural extension point only.

## 7. Lockfile verification

`uv lock --offline` regenerated the lock using the existing workstation cache and resolved 50 packages. `uv lock --check --offline` passes. No unrestricted environment installation was performed.

## 8. Environment constraints

No `.venv`, `venv`, `.python`, or `.packages` directory was created. No model weights, browser binaries, Docker images, or Supabase images were downloaded.

## 9. Quality evidence

- Full pytest: `104 passed`
- Ruff: PASS
- mypy: PASS, 58 source files
- Architecture contract: `6 passed`
- uv lock check: PASS
- `git diff --check`: PASS
- No Stage 2 persistence or infrastructure implementation started.

## 10. Stage 2 entry impact

This correction establishes the dependency/runtime baseline for Stage 2. Persistence, Supabase, SQLAlchemy implementation, migrations, and broader installation work remain subsequent tasks. C2-00 is ACCEPTED. The dependency/runtime correction is complete. Stage 2 platform persistence work may now proceed under the accepted implementation constraints.

C2-00 Baseline Version: 1.0
C2-00 Status: ACCEPTED
Acceptance Date: 2026-08-29
Accepted By: Project Control
DEC-IMPL-REMOTE-MODEL-001 Alignment: PASS
Dependency Graph Correction: PASS
Quality Gate: PASS
Next Task: Stage 2 Platform Persistence Foundation
