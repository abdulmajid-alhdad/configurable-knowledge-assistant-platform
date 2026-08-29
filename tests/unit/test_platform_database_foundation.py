"""Tests for platform database configuration and SQLAlchemy construction."""

from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import Engine

from knowledge_platform.config.database import PlatformDatabaseSettings
from knowledge_platform.infrastructure.persistence.database import (
    create_platform_engine,
    create_session_factory,
)


def test_valid_platform_database_settings_normalize_dsn() -> None:
    settings = PlatformDatabaseSettings(
        PLATFORM_DATABASE_DSN="  postgresql+psycopg://user:pass@localhost/platform  "
    )
    assert settings.dsn == "postgresql+psycopg://user:pass@localhost/platform"
    assert isinstance(settings.platform_database_dsn, SecretStr)
    assert "user:pass" not in repr(settings)


@pytest.mark.parametrize(
    "value",
    [
        "sqlite:///example.db",
        "mysql://user:secret@localhost/db",
        "postgresql://user:secret@localhost/db",
    ],
)
def test_non_postgresql_psycopg_dsn_is_rejected_without_secret_leak(
    value: str,
) -> None:
    with pytest.raises(ValidationError, match="postgresql\\+psycopg") as error:
        PlatformDatabaseSettings(PLATFORM_DATABASE_DSN=value)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_platform_database_dsn_is_rejected(value: str) -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        PlatformDatabaseSettings(PLATFORM_DATABASE_DSN=value)


def test_missing_platform_database_dsn_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PlatformDatabaseSettings(_env_file=None)


def test_engine_construction_does_not_connect() -> None:
    settings = PlatformDatabaseSettings(
        PLATFORM_DATABASE_DSN="postgresql+psycopg://user:pass@localhost/platform"
    )
    engine = create_platform_engine(settings)
    assert isinstance(engine, Engine)
    assert engine.url.get_backend_name() == "postgresql"
    assert engine.url.get_driver_name() == "psycopg"
    engine.dispose()


def test_session_factory_is_constructed_without_domain_framework_leak() -> None:
    settings = PlatformDatabaseSettings(
        PLATFORM_DATABASE_DSN="postgresql+psycopg://user:pass@localhost/platform"
    )
    factory = create_session_factory(create_platform_engine(settings))
    assert factory.class_.__name__ == "Session"


def test_settings_have_only_the_platform_dsn_field() -> None:
    assert list(PlatformDatabaseSettings.model_fields) == ["platform_database_dsn"]


def test_session_scope_uses_factory_begin_and_yields_session() -> None:
    factory = MagicMock()
    session = object()
    factory.begin.return_value.__enter__.return_value = session

    from knowledge_platform.infrastructure.persistence.database import session_scope

    with session_scope(factory) as yielded:
        assert yielded is session

    factory.begin.assert_called_once_with()
    factory.begin.return_value.__exit__.assert_called_once()


def test_session_scope_propagates_exception() -> None:
    factory = MagicMock()
    factory.begin.return_value.__enter__.return_value = object()

    from knowledge_platform.infrastructure.persistence.database import session_scope

    with pytest.raises(RuntimeError, match="boom"):
        with session_scope(factory):
            raise RuntimeError("boom")

    factory.begin.return_value.__exit__.assert_called_once()
