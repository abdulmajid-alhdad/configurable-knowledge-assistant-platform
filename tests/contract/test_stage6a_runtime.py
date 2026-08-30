from typing import Any, cast

import pytest
from pydantic import ValidationError

from knowledge_platform.config.runtime import RuntimeSettings
from knowledge_platform.infrastructure.credentials.environment import (
    EnvironmentCredentialResolver,
)
from knowledge_platform.modules.workspace_assistant.domain.security import CredentialReference


def _settings(**overrides: object) -> RuntimeSettings:
    values: dict[str, object] = {
        "KNOWLEDGE_PLATFORM_MODE": "production",
        "PLATFORM_DATABASE_DSN": "postgresql+psycopg://user:pass@example.test/db",
        "EMBEDDING_ENDPOINT": "https://embedding.test/v1",
        "EMBEDDING_MODEL_REFERENCE": "embedding-model",
        "EMBEDDING_CREDENTIAL_REFERENCE": "EMBEDDING_KEY",
        "EMBEDDING_DIMENSIONS": 3,
        "MODEL_ENDPOINT": "https://model.test/v1",
        "MODEL_REFERENCE": "model-reference",
        "MODEL_CREDENTIAL_REFERENCE": "MODEL_KEY",
    }
    values.update(overrides)
    return RuntimeSettings(**cast(dict[str, Any], values))


def test_production_settings_require_provider_configuration() -> None:
    assert _settings().mode == "production"
    with pytest.raises(ValidationError, match="provider configuration is incomplete"):
        _settings(MODEL_ENDPOINT=None)


def test_secret_dsn_is_not_rendered() -> None:
    settings = _settings()
    assert "pass@example" not in repr(settings)


def test_environment_credential_resolver_is_explicit_and_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = EnvironmentCredentialResolver()
    monkeypatch.setenv("MODEL_KEY", "test-secret")
    assert resolver.resolve(CredentialReference("MODEL_KEY")) == "test-secret"
    monkeypatch.delenv("MISSING_KEY", raising=False)
    with pytest.raises(RuntimeError, match="credential is unavailable") as error:
        resolver.resolve(CredentialReference("MISSING_KEY"))
    assert "test-secret" not in str(error.value)


def test_production_bootstrap_has_no_yemen_reference_import() -> None:
    source = open("src/knowledge_platform/bootstrap/application.py", encoding="utf-8").read()
    assert "reference.yemen_history" not in source
