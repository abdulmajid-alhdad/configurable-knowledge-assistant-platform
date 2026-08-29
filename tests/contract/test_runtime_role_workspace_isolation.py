"""Static security contract tests for the C2-03 migration foundation."""

from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
EXPECTED_MIGRATION = "20260829010000_runtime_role_workspace_context.sql"
RUNTIME_ROLE = "knowledge_platform_runtime"


def _migration_text() -> str:
    migration = MIGRATIONS_DIR / EXPECTED_MIGRATION
    assert migration.is_file()
    return migration.read_text(encoding="utf-8").lower()


def test_runtime_role_migration_exists() -> None:
    assert MIGRATIONS_DIR.is_dir()
    assert (MIGRATIONS_DIR / EXPECTED_MIGRATION).is_file()


def test_runtime_role_is_least_privilege() -> None:
    text = _migration_text()
    assert f"create role {RUNTIME_ROLE}" in text
    assert "login" in text
    restrictions = ("nosuperuser", "nobypassrls", "nocreatedb", "nocreaterole", "noreplication")
    for restriction in restrictions:
        assert restriction in text
    assert "password" not in text
    assert "credential" not in text


def test_existing_role_attributes_are_validated_fail_closed() -> None:
    text = _migration_text()
    assert "pg_roles%rowtype" in text
    for attribute in (
        "rolcanlogin",
        "rolsuper",
        "rolbypassrls",
        "rolcreatedb",
        "rolcreaterole",
        "rolreplication",
    ):
        assert attribute in text
    assert "raise exception" in text
    assert "unsafe attributes" in text


def test_membership_and_ownership_are_rejected_fail_closed() -> None:
    text = _migration_text()
    assert "pg_auth_members" in text
    assert "unexpected role membership" in text
    assert "pg_namespace" in text
    assert "nspowner" in text
    assert "owns a private schema" in text


def test_runtime_role_has_schema_usage_only() -> None:
    text = _migration_text()
    for schema in ("platform", "retrieval", "evaluation"):
        assert f"revoke create on schema {schema} from {RUNTIME_ROLE}" in text
        assert f"grant usage on schema {schema} to {RUNTIME_ROLE}" in text
    assert "grant create on schema" not in text


def test_effective_create_privilege_is_checked_and_rejected() -> None:
    text = _migration_text()
    assert "has_schema_privilege" in text
    assert "'create'" in text
    assert "retains create on schema" in text


def test_no_broad_exposure_or_business_objects() -> None:
    text = _migration_text()
    for marker in (
        " to public",
        " to anon",
        " to authenticated",
        "create table",
        "create policy",
        "enable row level security",
        "create view",
        "create function",
    ):
        assert marker not in text


def test_workspace_context_is_transaction_local_and_fail_closed() -> None:
    text = _migration_text()
    assert "set_config('app.workspace_id'" in text
    assert ", true)" in text
    assert "current_setting('app.workspace_id', true)::uuid" in text
    assert "missing or malformed values must fail closed" in text


def test_no_role_or_privilege_escalation() -> None:
    text = _migration_text()
    assert "alter role" not in text
    assert "grant all" not in text
    assert "replication" in text
