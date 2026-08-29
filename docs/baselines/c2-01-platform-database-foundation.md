# C2-01  Platform Database Configuration & SQLAlchemy Foundation

Version: 1.0
Status: ACCEPTED
Stage: 2  Platform Foundation & Core Slices
Project: Configurable Knowledge Assistant Platform

## 1. Purpose

Establish the minimal configuration and SQLAlchemy runtime foundation for the platform-owned PostgreSQL persistence boundary.

## 2. Scope

C2-01 provides validated platform database settings, PostgreSQL/Psycopg engine construction, session factory creation, and a controlled transaction boundary. It does not define platform tables or persistence entities.

## 3. Platform DB vs Knowledge DB boundary

The platform database is owned by this application for future platform metadata. External user knowledge databases and their adapters are separate concerns and are not implemented here.

## 4. PlatformDatabaseSettings

`PlatformDatabaseSettings` uses `pydantic-settings` and the `PLATFORM_DATABASE_DSN` environment variable. The DSN is required, must be non-blank after trimming, and must use the accepted `postgresql+psycopg` scheme. It is represented as `SecretStr` so normal representations do not expose credentials.

## 5. SQLAlchemy engine/session foundation

`create_platform_engine(settings)` constructs a SQLAlchemy 2.x engine using the validated PostgreSQL Psycopg DSN. Construction does not open a database connection. `create_session_factory(engine)` creates a typed SQLAlchemy session factory without creating tables.

## 6. Transaction/session boundary

`session_scope(factory)` yields a transaction-scoped session using SQLAlchemy's context-managed `begin()` boundary. Failures propagate and are not converted into success. No repository or Unit of Work abstraction is introduced.

## 7. Secret and failure handling

Database configuration is outside Domain modules. No DSN is stored in domain objects, and no connection is attempted by importing domain code. Missing, blank, malformed, or wrong-driver configuration fails explicitly when settings are requested. `SecretStr` and `repr` protection are used, Pydantic validation-error input values are hidden, and malformed/wrong-driver DSNs do not expose raw credential values. No credentials are logged or placed in error messages by this foundation.

## 8. Explicit non-goals

No ORM entities, metadata creation, tables, migrations, RLS policies, Supabase schemas, external knowledge-source adapters, live database connectivity, API routes, or model/embedding adapters are included.

## 9. Test evidence

- Focused C2-01 tests: `12 passed`
- Full pytest: `116 passed`
- Ruff: PASS
- mypy: PASS, 60 source files
- Architecture contract: `6 passed`
- Dependency declarations were unchanged during C2-01. `uv lock --check --offline` passed before the final source/test-only correction. The final rerun was blocked by a workstation uv-cache ACL error (`sdists-v9/.git`: Access is denied). Because neither `pyproject.toml` nor `uv.lock` changed, the previously successful lock verification remains the accepted dependency-integrity evidence for C2-01.
- `git diff --check`: PASS
- No live database connection was attempted.

## 10. Architecture compliance

Domain remains framework-independent and imports no SQLAlchemy, Psycopg, or Pydantic Settings. Framework dependencies are confined to configuration and infrastructure layers.

## 11. Runtime environment note

The workstation Python 3.13 runtime was enabled with the exact locked C2-01 packages: pydantic 2.13.4, pydantic-settings 2.15.0, SQLAlchemy 2.0.52, and Psycopg 3.3.4. No project virtual environment is used. `pyproject.toml` and `uv.lock` remain the reproducibility authority. No model runtime or model weights were installed.

## 12. Next persistence step

The next authorized persistence work may define version-controlled schema/migration boundaries. C2-01 itself creates no schema and makes no live database connection.

Accepted DSN scheme: `postgresql+psycopg`.
Wrong backend and wrong PostgreSQL driver DSNs are rejected.
Validation input values are hidden from error output; credentials are not exposed in normal representations or validation errors.
`session_scope` is directly tested, including exception propagation.
No live database connection, ORM entities, migrations, RLS, Supabase schemas, project virtual environment, model runtime, or model weights were created or installed.

C2-01 Baseline Version: 1.0
C2-01 Status: ACCEPTED
Acceptance Date: 2026-08-29
Accepted By: Project Control
Platform Database Boundary: PASS
Secret Handling: PASS
Transaction Boundary: PASS
Domain Framework Isolation: PASS
Quality Gate: PASS
Dependency Integrity Evidence: ACCEPTED FROM PRIOR SUCCESSFUL LOCK CHECK
Next Task: Stage 2 Schema & Migration Foundation
