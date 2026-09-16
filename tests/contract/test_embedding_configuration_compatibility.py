"""Focused safety contracts for embedding runtime configuration changes."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from knowledge_platform.application.provider_configuration import (
    ModelCapability,
    ProviderConfigurationConflict,
    ProviderConfigurationInput,
    ProviderConfigurationResolver,
    ProviderConfigurationService,
    ProviderDefinition,
    StoredProviderConfiguration,
)
from knowledge_platform.infrastructure.provider_configuration import (
    EnvironmentProviderConfiguration,
)
from knowledge_platform.modules.access_control.domain import Permission

ROOT = Path(__file__).resolve().parents[2]
ACTOR = UUID("00000000-0000-0000-0000-000000000123")


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class Access:
    def require_system(self, actor: UUID, permission: Permission) -> None:
        assert actor == ACTOR
        assert permission is Permission.PROVIDERS_MANAGE


class Store:
    def __init__(
        self,
        values: dict[ModelCapability, StoredProviderConfiguration] | None = None,
    ) -> None:
        self.values = values or {}
        self.saved: ProviderConfigurationInput | None = None

    def configuration(
        self, capability: ModelCapability
    ) -> StoredProviderConfiguration | None:
        return self.values.get(capability)

    @staticmethod
    def providers() -> tuple[ProviderDefinition, ...]:
        return (
            ProviderDefinition("openrouter", "OpenRouter", "multi", None),
            ProviderDefinition("other", "Other", "embeddings", None),
        )

    def save(
        self,
        actor: UUID,
        value: ProviderConfigurationInput,
        request_id: str | None,
    ) -> StoredProviderConfiguration:
        assert actor == ACTOR
        assert request_id is None
        self.saved = value
        stored = StoredProviderConfiguration(
            id=UUID("00000000-0000-0000-0000-000000000777"),
            capability=value.capability,
            provider=value.provider,
            model_id=value.model_id,
            endpoint=value.endpoint,
            credential_reference=value.credential_reference,
            dimensions=value.dimensions,
            active=value.active,
            created_by=actor,
            created_at=datetime(2026, 9, 15, tzinfo=UTC),
        )
        self.values[value.capability] = stored
        return stored


class IndexState:
    def __init__(self, indexed: bool) -> None:
        self.indexed = indexed
        self.calls = 0

    def has_indexed_embeddings(self) -> bool:
        self.calls += 1
        return self.indexed


def environment(
    *,
    model_id: str = "baai/bge-m3",
    endpoint: str = "https://openrouter.ai/api/v1/embeddings",
    credential_reference: str = "OPENROUTER_API_KEY",
    dimensions: int = 1024,
) -> EnvironmentProviderConfiguration:
    return EnvironmentProviderConfiguration(
        generation_endpoint="https://openrouter.ai/api/v1/chat/completions",
        generation_model="mistralai/mistral-nemo",
        generation_credential_reference="OPENROUTER_API_KEY",
        embedding_endpoint=endpoint,
        embedding_model=model_id,
        embedding_credential_reference=credential_reference,
        embedding_dimensions=dimensions,
    )


def stored_embedding(
    *,
    provider: str = "openrouter",
    model_id: str = "persisted/embedding-a",
    endpoint: str = "https://openrouter.ai/api/v1/embeddings-a",
    credential_reference: str = "OPENROUTER_API_KEY",
    dimensions: int = 1024,
) -> StoredProviderConfiguration:
    return StoredProviderConfiguration(
        id=UUID("00000000-0000-0000-0000-000000000555"),
        capability=ModelCapability.EMBEDDING,
        provider=provider,
        model_id=model_id,
        endpoint=endpoint,
        credential_reference=credential_reference,
        dimensions=dimensions,
        active=True,
        created_by=ACTOR,
        created_at=datetime(2026, 9, 15, tzinfo=UTC),
    )


def service(
    store: Store,
    index_state: IndexState,
    *,
    fallback: EnvironmentProviderConfiguration | None = None,
) -> ProviderConfigurationService:
    fallback = fallback or environment()
    return ProviderConfigurationService(
        access=Access(),  # type: ignore[arg-type]
        resolver=ProviderConfigurationResolver(store=store, fallback=fallback),
        store=store,
        fallback=fallback,
        embedding_index_state=index_state,
    )


def configure(
    control: ProviderConfigurationService,
    capability: ModelCapability,
    *,
    model_id: str,
    dimensions: int | None,
    provider: str = "openrouter",
    endpoint: str | None = None,
    credential_reference: str = "OPENROUTER_API_KEY",
    active: bool = True,
) -> dict[str, object]:
    if endpoint is None:
        endpoint = (
            "https://openrouter.ai/api/v1/embeddings"
            if capability is ModelCapability.EMBEDDING
            else "https://openrouter.ai/api/v1/chat/completions"
        )
    return control.configure(
        ACTOR,
        capability,
        provider=provider,
        model_id=model_id,
        endpoint=endpoint,
        credential_reference=credential_reference,
        dimensions=dimensions,
        active=active,
    )


def test_generation_model_change_is_unaffected_by_index_compatibility_guard() -> None:
    store = Store()
    index_state = IndexState(indexed=True)

    result = configure(
        service(store, index_state),
        ModelCapability.GENERATION,
        model_id="vendor/new-generation",
        dimensions=None,
    )

    assert result["effective"]["model_id"] == "vendor/new-generation"  # type: ignore[index]
    assert store.saved is not None
    assert index_state.calls == 0


def test_embedding_model_change_with_indexed_vectors_is_rejected_before_save() -> None:
    store = Store({ModelCapability.EMBEDDING: stored_embedding()})
    index_state = IndexState(indexed=True)

    with pytest.raises(
        ProviderConfigurationConflict, match="EMBEDDING_REINDEX_REQUIRED"
    ):
        configure(
            service(store, index_state),
            ModelCapability.EMBEDDING,
            model_id="vendor/different-embedding",
            endpoint="https://openrouter.ai/api/v1/embeddings-a",
            dimensions=1024,
        )

    assert store.saved is None
    assert index_state.calls == 1


def test_embedding_dimension_change_with_indexed_vectors_is_rejected_before_save() -> None:
    store = Store({ModelCapability.EMBEDDING: stored_embedding()})
    index_state = IndexState(indexed=True)

    with pytest.raises(
        ProviderConfigurationConflict, match="EMBEDDING_REINDEX_REQUIRED"
    ):
        configure(
            service(store, index_state),
            ModelCapability.EMBEDDING,
            model_id="persisted/embedding-a",
            endpoint="https://openrouter.ai/api/v1/embeddings-a",
            dimensions=768,
        )

    assert store.saved is None
    assert index_state.calls == 1


def test_embedding_provider_change_with_indexed_vectors_is_rejected() -> None:
    store = Store({ModelCapability.EMBEDDING: stored_embedding()})
    index_state = IndexState(indexed=True)

    with pytest.raises(
        ProviderConfigurationConflict, match="EMBEDDING_REINDEX_REQUIRED"
    ):
        configure(
            service(store, index_state),
            ModelCapability.EMBEDDING,
            provider="other",
            model_id="persisted/embedding-a",
            endpoint="https://openrouter.ai/api/v1/embeddings-a",
            dimensions=1024,
        )

    assert store.saved is None
    assert index_state.calls == 1


def test_embedding_endpoint_change_with_indexed_vectors_is_rejected() -> None:
    store = Store({ModelCapability.EMBEDDING: stored_embedding()})
    index_state = IndexState(indexed=True)

    with pytest.raises(
        ProviderConfigurationConflict, match="EMBEDDING_REINDEX_REQUIRED"
    ):
        configure(
            service(store, index_state),
            ModelCapability.EMBEDDING,
            model_id="persisted/embedding-a",
            endpoint="https://openrouter.ai/api/v1/embeddings-b",
            dimensions=1024,
        )

    assert store.saved is None
    assert index_state.calls == 1


def test_embedding_credential_only_change_is_allowed_without_index_query() -> None:
    store = Store({ModelCapability.EMBEDDING: stored_embedding()})
    index_state = IndexState(indexed=True)

    configure(
        service(store, index_state),
        ModelCapability.EMBEDDING,
        model_id="persisted/embedding-a",
        endpoint="https://openrouter.ai/api/v1/embeddings-a",
        credential_reference="ROTATED_OPENROUTER_API_KEY",
        dimensions=1024,
    )

    assert store.saved is not None
    assert index_state.calls == 0


def test_deactivating_to_different_fallback_is_rejected_when_indexed() -> None:
    store = Store({ModelCapability.EMBEDDING: stored_embedding()})
    index_state = IndexState(indexed=True)

    with pytest.raises(
        ProviderConfigurationConflict, match="EMBEDDING_REINDEX_REQUIRED"
    ):
        configure(
            service(store, index_state, fallback=environment()),
            ModelCapability.EMBEDDING,
            model_id="persisted/embedding-a",
            endpoint="https://openrouter.ai/api/v1/embeddings-a",
            dimensions=1024,
            active=False,
        )

    assert store.saved is None
    assert index_state.calls == 1


def test_deactivating_to_semantically_identical_fallback_is_allowed() -> None:
    current = stored_embedding()
    assert current.dimensions is not None
    store = Store({ModelCapability.EMBEDDING: current})
    index_state = IndexState(indexed=True)
    fallback = environment(
        model_id=current.model_id,
        endpoint=current.endpoint,
        credential_reference="FALLBACK_OPENROUTER_API_KEY",
        dimensions=current.dimensions,
    )

    result = configure(
        service(store, index_state, fallback=fallback),
        ModelCapability.EMBEDDING,
        model_id=current.model_id,
        endpoint=current.endpoint,
        dimensions=current.dimensions,
        active=False,
    )

    assert result["effective"]["source"] == "ENVIRONMENT_FALLBACK"  # type: ignore[index]
    assert store.saved is not None
    assert index_state.calls == 0


def test_inactive_persisted_value_does_not_change_current_fallback() -> None:
    store = Store()
    index_state = IndexState(indexed=True)

    result = configure(
        service(store, index_state),
        ModelCapability.EMBEDDING,
        model_id="stored/but-inactive",
        endpoint="https://openrouter.ai/api/v1/inactive-embeddings",
        dimensions=768,
        active=False,
    )

    assert result["effective"]["model_id"] == "baai/bge-m3"  # type: ignore[index]
    assert store.saved is not None
    assert store.saved.active is False
    assert index_state.calls == 0


def test_activating_different_embedding_from_fallback_is_rejected() -> None:
    store = Store()
    index_state = IndexState(indexed=True)

    with pytest.raises(
        ProviderConfigurationConflict, match="EMBEDDING_REINDEX_REQUIRED"
    ):
        configure(
            service(store, index_state),
            ModelCapability.EMBEDDING,
            model_id="persisted/new-embedding",
            endpoint="https://openrouter.ai/api/v1/new-embeddings",
            dimensions=768,
            active=True,
        )

    assert store.saved is None
    assert index_state.calls == 1


def test_unchanged_embedding_semantics_skip_index_query() -> None:
    store = Store({ModelCapability.EMBEDDING: stored_embedding()})
    index_state = IndexState(indexed=True)

    result = configure(
        service(store, index_state),
        ModelCapability.EMBEDDING,
        model_id="persisted/embedding-a",
        endpoint="https://openrouter.ai/api/v1/embeddings-a",
        dimensions=1024,
    )

    assert result["effective"]["model_id"] == "persisted/embedding-a"  # type: ignore[index]
    assert store.saved is not None
    assert index_state.calls == 0


def test_embedding_change_without_indexed_vectors_uses_existing_save_validation() -> None:
    store = Store()
    index_state = IndexState(indexed=False)

    result = configure(
        service(store, index_state),
        ModelCapability.EMBEDDING,
        model_id="vendor/new-embedding",
        dimensions=768,
    )

    assert result["effective"]["model_id"] == "vendor/new-embedding"  # type: ignore[index]
    assert store.saved is not None
    assert index_state.calls == 1


def test_index_state_boundary_is_authoritative_read_only_and_system_protected() -> None:
    persistence = read(
        "src/knowledge_platform/infrastructure/provider_configuration/persistence.py"
    )
    migration = read(
        "supabase/migrations/"
        "20260915002500_embedding_runtime_compatibility_guard.sql"
    ).lower()
    application = read("src/knowledge_platform/application/provider_configuration.py")

    assert "select platform.has_indexed_embeddings()" in persistence
    assert "return exists" in migration
    assert "from retrieval.document_chunks" in migration
    assert "security definer" in migration
    assert "set search_path = ''" in migration
    assert "set row_security = off" in migration
    assert "user_has_system_permission('providers.manage')" in migration
    assert "from public, anon, authenticated" in migration
    assert "to knowledge_platform_runtime" in migration
    assert "select 1" in migration
    assert "<=>" not in migration
    assert "embed_query(" not in application
    assert "vector" not in application.lower()
    assert "generate(" not in application


def test_delivery_and_frontend_expose_bounded_reindex_conflict() -> None:
    delivery = read("src/knowledge_platform/delivery/provider_configuration_api.py")
    frontend = read("frontend/system/controls-pages.js")

    assert "except ProviderConfigurationConflict as exc" in delivery
    assert "HTTPException(status_code=409" in delivery
    assert 'error.code === "EMBEDDING_REINDEX_REQUIRED"' in frontend
    assert (
        "لا يمكن تغيير نموذج التمثيلات أو أبعاده مع وجود معرفة مفهرسة. "
        "يلزم مسار إعادة فهرسة معتمد قبل هذا التغيير."
    ) in frontend
