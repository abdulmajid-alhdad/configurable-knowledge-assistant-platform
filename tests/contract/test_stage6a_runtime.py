from typing import Any, cast

import pytest
from pydantic import ValidationError

from knowledge_platform.bootstrap.application import ApplicationRuntime
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
        "SUPABASE_AUTH_URL": "https://identity.test",
        "SUPABASE_PUBLISHABLE_KEY": "publishable-test-key",
    }
    values.update(overrides)
    return RuntimeSettings(**cast(dict[str, Any], values))


def test_production_settings_allow_persisted_config_without_environment_fallback() -> None:
    settings = _settings(
        MODEL_ENDPOINT=None,
        MODEL_REFERENCE=None,
        MODEL_CREDENTIAL_REFERENCE=None,
        EMBEDDING_ENDPOINT=None,
        EMBEDDING_MODEL_REFERENCE=None,
        EMBEDDING_CREDENTIAL_REFERENCE=None,
        EMBEDDING_DIMENSIONS=None,
    )

    assert settings.mode == "production"
    assert settings.model_endpoint is None
    assert settings.embedding_endpoint is None


def test_retrieval_distance_defaults_to_calibrated_value() -> None:
    assert _settings().max_retrieval_distance == 0.4


def test_retrieval_distance_accepts_explicit_override() -> None:
    assert _settings(MAX_RETRIEVAL_DISTANCE=0.35).max_retrieval_distance == 0.35


@pytest.mark.parametrize("value", (0.0, 0.4, 1.0, 1.5, 2.0))
def test_retrieval_distance_accepts_cosine_distance_range(value: float) -> None:
    assert _settings(MAX_RETRIEVAL_DISTANCE=value).max_retrieval_distance == value


@pytest.mark.parametrize(
    "value", (-0.01, 2.01, float("nan"), float("inf"), float("-inf"))
)
def test_retrieval_distance_rejects_values_outside_cosine_range(value: float) -> None:
    with pytest.raises(ValidationError, match="max retrieval distance"):
        _settings(MAX_RETRIEVAL_DISTANCE=value)


def test_production_rag_composition_receives_configured_distance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Captured:
        def __init__(self, **kwargs: object) -> None:
            self.distance = kwargs["max_retrieval_distance"]

    class Vectors:
        def __init__(self, session: object) -> None:
            pass

    settings = _settings(MAX_RETRIEVAL_DISTANCE=0.35)
    runtime = ApplicationRuntime(
        settings=settings,
        engine=object(),
        session_factory=object(),
        credentials=object(),
        egress=object(),
    )
    monkeypatch.setattr("knowledge_platform.bootstrap.application.DocumentRagService", Captured)
    monkeypatch.setattr(
        "knowledge_platform.bootstrap.application.PgvectorDocumentSearchAdapter", Vectors
    )
    monkeypatch.setattr(ApplicationRuntime, "embedding_gateway", lambda self: object())
    monkeypatch.setattr(ApplicationRuntime, "model_gateway", lambda self: object())

    rag = runtime.rag_service(object())

    assert rag.distance == 0.35


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


def test_environment_credential_resolver_strips_surrounding_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_KEY", "  test-secret\r\n")
    assert (
        EnvironmentCredentialResolver().resolve(CredentialReference("MODEL_KEY"))
        == "test-secret"
    )


def test_environment_credential_resolver_rejects_blank_after_trim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_KEY", " \r\n\t")
    with pytest.raises(RuntimeError, match="credential is unavailable"):
        EnvironmentCredentialResolver().resolve(CredentialReference("MODEL_KEY"))


def test_production_bootstrap_has_no_yemen_reference_import() -> None:
    source = open("src/knowledge_platform/bootstrap/application.py", encoding="utf-8").read()
    assert "reference.yemen_history" not in source
