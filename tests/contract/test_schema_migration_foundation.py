"""Static contract tests for the C2-02 migration foundation."""

from __future__ import annotations

from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
EXPECTED_MIGRATION = "20260829000000_create_private_schemas.sql"


def _migration_text() -> str:
    migration = MIGRATIONS_DIR / EXPECTED_MIGRATION
    assert migration.is_file()
    return migration.read_text(encoding="utf-8").lower()


def test_migration_directory_exists() -> None:
    assert MIGRATIONS_DIR.is_dir()


def test_expected_foundational_migration_exists() -> None:
    assert (MIGRATIONS_DIR / EXPECTED_MIGRATION).is_file()


def test_private_schemas_use_if_not_exists() -> None:
    text = _migration_text()
    for schema in ("platform", "retrieval", "evaluation"):
        assert f"create schema if not exists {schema}" in text


def test_migration_contains_no_tables_rls_or_broad_grants() -> None:
    text = _migration_text()
    assert "create table" not in text
    assert "create policy" not in text
    assert "grant all" not in text
    assert " to public" not in text
    assert " to anon" not in text
    assert " to authenticated" not in text


def test_alembic_is_not_introduced() -> None:
    assert not (MIGRATIONS_DIR.parent.parent / "alembic.ini").exists()
    assert "alembic" not in _migration_text()
