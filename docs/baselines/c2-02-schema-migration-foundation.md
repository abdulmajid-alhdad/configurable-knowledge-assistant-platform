# C2-02  Schema & Migration Foundation

Version: 1.0
Status: ACCEPTED
Stage: 2  Platform Foundation & Core Slices
Project: Configurable Knowledge Assistant Platform

## 1. Purpose

Establish the version-controlled Supabase-style SQL migration foundation and private platform schema namespaces.

## 2. Scope

C2-02 adds one deterministic foundational migration and static artifact tests. It creates no application tables or runtime database behavior.

## 3. Migration mechanism

Supabase SQL migrations under `supabase/migrations/` are authoritative. Alembic is not used, and no custom migration runner is introduced.

## 4. Private schema boundary

The private application-owned schemas are `platform`, `retrieval`, and `evaluation`. External user knowledge databases remain outside platform persistence.

## 5. Initial migration artifact

`20260829000000_create_private_schemas.sql` creates only the three schemas with `CREATE SCHEMA IF NOT EXISTS`. No application tables exist yet.

## 6. Security/exposure constraints

No broad grants to `public`, `anon`, or `authenticated` are present. No public views or functions, runtime database role, RLS policies, Supabase credentials, or Data API exposure are created.

## 7. Explicit non-goals

No ORM entities, repositories, application tables, metadata creation, migrations executed against a live database, RLS, runtime roles, Supabase provisioning, or external knowledge-source adapters are included.

## 8. Static validation strategy

Artifact-based tests verify the migration directory, deterministic migration, schema declarations, `IF NOT EXISTS`, and absence of tables, RLS, broad grants, and Alembic.

## 9. Quality evidence

Quality evidence:

- Targeted C2-02 tests: `5 passed`
- Full pytest: `121 passed`
- Ruff: PASS
- mypy: PASS, 60 source files
- Architecture contract: `6 passed`
- `git diff --check`: PASS
- `pyproject.toml`: unchanged
- `uv.lock`: unchanged

The latest local `uv lock --check --offline` rerun was blocked by the known workstation uv-cache ACL error (`sdists-v9/.git`: Access is denied). C2-02 introduced no dependency changes, and both `pyproject.toml` and `uv.lock` remained unchanged. Tests are offline/static and require no PostgreSQL, Supabase, Docker, or network access.

## 10. Architecture compliance

Migration artifacts remain external, version controlled, and separate from framework-independent Domain code. Python startup does not execute migrations or create schemas.

## 11. Next persistence/security step

The next authorized security foundation will define the runtime database role and workspace-isolation/RLS boundary. Application persistence tables remain subsequent work.

Next Task: C2-03  Runtime DB Role + Workspace Isolation/RLS Foundation

C2-02 Baseline Version: 1.0
C2-02 Status: ACCEPTED
Acceptance Date: 2026-08-29
Accepted By: Project Control
Migration Mechanism: PASS
Private Schema Boundary: PASS
Security Scope Discipline: PASS
Application Tables Created: NO
RLS Created: NO
Runtime Role Created: NO
Live Migration Executed: NO
Dependency Changes: NO
Quality Gate: PASS
Next Task: C2-03  Runtime DB Role + Workspace Isolation/RLS Foundation
