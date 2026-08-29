# C2-03  Runtime DB Role + Workspace Isolation/RLS Foundation

Version: 1.0
Status: ACCEPTED
Stage: 2  Platform Foundation & Core Slices
Project: Configurable Knowledge Assistant Platform

## 1. Purpose

Define the least-privilege runtime database role and trusted workspace-isolation context for future platform persistence.

## 2. Threat/security boundary

Workspace authorization originates from trusted application authorization context. Prompt, history, retrieved content, and model output cannot grant or override workspace access. RLS is defense in depth, not the only authorization layer.

## 3. Runtime database role

The migration creates the stable `knowledge_platform_runtime` role with login capability and safe least-privilege attributes when absent. If it already exists, all required `pg_roles` attributes are validated; an unsafe pre-existing role causes the migration to abort. Unexpected role membership and ownership of any private schema also cause the migration to abort. No password is stored in Git; operational credential provisioning remains environment-specific.

## 4. Schema privileges

The migration explicitly revokes `CREATE` from the runtime role on the private `platform`, `retrieval`, and `evaluation` schemas, then grants `USAGE` only. It verifies effective `CREATE` privilege with `has_schema_privilege` and aborts if any remains. It adds no broad public, `anon`, or `authenticated` grants.

## 5. Trusted workspace context

Application persistence code supplies the trusted workspace identity. No SQL setter accepting arbitrary authorization input is exposed by this foundation.

## 6. Transaction-local app.workspace_id

The convention is `set_config('app.workspace_id', '<trusted-workspace-uuid>', true)`, where `true` makes the setting transaction-local rather than persistent session state.

## 7. RLS fail-closed convention

Future workspace-scoped policies use `workspace_id = current_setting('app.workspace_id', true)::uuid`. Missing `app.workspace_id` yields `NULL` and the predicate does not match. A valid UUID may match only the same `workspace_id`. Blank or malformed non-UUID input causes the UUID cast to fail and the database operation to fail. No case provides unrestricted workspace access. No policies are created against nonexistent business tables in C2-03.

## 8. Credential provisioning boundary

No real database password or secret is committed. Runtime credential provisioning belongs to deployment/environment configuration and later security work.

## 9. Explicit non-goals

No business tables, ORM entities, repositories, CRUD, live database migration, Supabase provisioning, RLS policies, runtime database role password, or application routes are included.

## 10. Static validation strategy

Artifact-based tests verify role restrictions, schema `USAGE`-only grants, absence of broad exposure and business objects, and the transaction-local fail-closed workspace context convention.

## 11. Quality evidence

Static security validation: PERFORMED. Actual PostgreSQL migration/parser execution: NOT YET PERFORMED.

Quality evidence:

- Targeted C2-03 tests: `9 passed`
- Full pytest: `130 passed`
- Ruff: PASS
- mypy: PASS, 60 source files
- Architecture contract: `6 passed`
- `git diff --check`: PASS
- `pyproject.toml`: unchanged
- `uv.lock`: unchanged

The final local `uv lock --check --offline` rerun was blocked by the known workstation uv-cache ACL issue (`sdists-v9/.git`: Access is denied). C2-03 introduced no Python dependency changes; `pyproject.toml` and `uv.lock` remained unchanged. Tests are static and require no PostgreSQL, Supabase, Docker, or network access.

## 12. Next persistence step

Next Task: C2-04  Workspace & Assistant Persistence Slice. Later migrations may introduce business tables and table-specific RLS policies using this convention.

C2-03 Baseline Version: 1.0
C2-03 Status: ACCEPTED
Acceptance Date: 2026-08-29
Accepted By: Project Control
Runtime Role Attributes: PASS
Existing Role Fail-Closed Validation: PASS
Role Membership Isolation: PASS
Private Schema Ownership Isolation: PASS
Direct CREATE Revocation: PASS
Effective CREATE Privilege Validation: PASS
Schema USAGE Boundary: PASS
Workspace Context Contract: PASS
Fail-Closed RLS Convention: PASS
Business Tables Created: NO
ORM Entities Created: NO
Repositories Created: NO
Table-Specific RLS Policies Created: NO
Application Workspace Setter Implemented: NO
Live Migration Executed: NO
Supabase Project Modified: NO
Dependency Changes: NO
Quality Gate: PASS
Next Task: C2-04  Workspace & Assistant Persistence Slice
