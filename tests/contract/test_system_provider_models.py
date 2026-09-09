"""Focused contracts for canonical provider/model configuration resolution."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from knowledge_platform.application.provider_configuration import (
    ConfigurationSource,
    ModelCapability,
    ProviderConfigurationError,
    ProviderConfigurationInput,
    ProviderConfigurationResolver,
    ProviderConfigurationService,
    ProviderDefinition,
    ResolvedProviderConfiguration,
    StoredProviderConfiguration,
)
from knowledge_platform.infrastructure.provider_configuration import (
    EnvironmentProviderConfiguration,
    RemoteProviderAdapterFactory,
)
from knowledge_platform.modules.access_control.domain import Permission
from knowledge_platform.modules.workspace_assistant.domain.security import (
    CredentialReference,
)

ROOT = Path(__file__).resolve().parents[2]
ACTOR = UUID("00000000-0000-0000-0000-000000000123")


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def fallback() -> EnvironmentProviderConfiguration:
    return EnvironmentProviderConfiguration(
        generation_endpoint="https://openrouter.ai/api/v1/chat/completions",
        generation_model="mistralai/mistral-nemo",
        generation_credential_reference="OPENROUTER_API_KEY",
        embedding_endpoint="https://openrouter.ai/api/v1/embeddings",
        embedding_model="baai/bge-m3",
        embedding_credential_reference="OPENROUTER_API_KEY",
        embedding_dimensions=1024,
    )


class Store:
    def __init__(
        self, values: dict[ModelCapability, StoredProviderConfiguration] | None = None
    ) -> None:
        self.values = values or {}
        self.saved: ProviderConfigurationInput | None = None

    def configuration(
        self, capability: ModelCapability
    ) -> StoredProviderConfiguration | None:
        return self.values.get(capability)

    def providers(self) -> tuple[ProviderDefinition, ...]:
        return (ProviderDefinition("openrouter", "OpenRouter", "multi", None),)

    def save(
        self,
        actor: UUID,
        value: ProviderConfigurationInput,
        request_id: str | None,
    ) -> StoredProviderConfiguration:
        assert actor == ACTOR
        assert request_id != "secret"
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
            created_at=datetime(2026, 9, 9, tzinfo=UTC),
        )
        self.values[value.capability] = stored
        return stored


def stored(
    capability: ModelCapability,
    *,
    model: str,
    endpoint: str,
    dimensions: int | None = None,
    active: bool = True,
) -> StoredProviderConfiguration:
    return StoredProviderConfiguration(
        id=UUID("00000000-0000-0000-0000-000000000456"),
        capability=capability,
        provider="openrouter",
        model_id=model,
        endpoint=endpoint,
        credential_reference="OPENROUTER_API_KEY",
        dimensions=dimensions,
        active=active,
        created_by=ACTOR,
        created_at=datetime(2026, 9, 9, tzinfo=UTC),
    )


def test_persisted_configuration_atomically_overrides_environment() -> None:
    store = Store(
        {
            ModelCapability.GENERATION: stored(
                ModelCapability.GENERATION,
                model="vendor/persisted-generation",
                endpoint="https://configured.example/v1/chat",
            ),
            ModelCapability.EMBEDDING: stored(
                ModelCapability.EMBEDDING,
                model="vendor/persisted-embedding",
                endpoint="https://configured.example/v1/embeddings",
                dimensions=768,
            ),
        }
    )
    resolver = ProviderConfigurationResolver(store=store, fallback=fallback())

    generation = resolver.resolve(ModelCapability.GENERATION)
    embedding = resolver.resolve(ModelCapability.EMBEDDING)

    assert generation.source is ConfigurationSource.PERSISTED
    assert generation.model_id == "vendor/persisted-generation"
    assert generation.endpoint == "https://configured.example/v1/chat"
    assert embedding.source is ConfigurationSource.PERSISTED
    assert embedding.model_id == "vendor/persisted-embedding"
    assert embedding.dimensions == 768


def test_absent_or_inactive_persisted_configuration_uses_complete_fallback() -> None:
    store = Store(
        {
            ModelCapability.GENERATION: stored(
                ModelCapability.GENERATION,
                model="vendor/inactive",
                endpoint="https://configured.example/v1/chat",
                active=False,
            )
        }
    )
    resolver = ProviderConfigurationResolver(store=store, fallback=fallback())

    generation = resolver.resolve(ModelCapability.GENERATION)
    embedding = resolver.resolve(ModelCapability.EMBEDDING)

    assert generation.source is ConfigurationSource.ENVIRONMENT_FALLBACK
    assert generation.model_id == "mistralai/mistral-nemo"
    assert embedding.source is ConfigurationSource.ENVIRONMENT_FALLBACK
    assert embedding.model_id == "baai/bge-m3"
    assert embedding.dimensions == 1024


def test_invalid_active_persisted_configuration_fails_closed_without_mixing() -> None:
    store = Store(
        {
            ModelCapability.GENERATION: stored(
                ModelCapability.GENERATION,
                model="vendor/broken",
                endpoint="http://insecure.example/v1/chat",
            )
        }
    )
    resolver = ProviderConfigurationResolver(store=store, fallback=fallback())

    with pytest.raises(
        ProviderConfigurationError, match="REMOTE_HTTPS_ENDPOINT_REQUIRED"
    ):
        resolver.resolve(ModelCapability.GENERATION)


def test_provider_support_and_embedding_dimensions_are_authoritative() -> None:
    store = Store()
    unsupported = ResolvedProviderConfiguration(
        capability=ModelCapability.GENERATION,
        provider="unknown",
        model_id="vendor/model",
        endpoint="https://provider.example/v1/chat",
        credential_reference="PROVIDER_API_KEY",
        dimensions=None,
        source=ConfigurationSource.PERSISTED,
    )
    invalid_embedding = ResolvedProviderConfiguration(
        capability=ModelCapability.EMBEDDING,
        provider="openrouter",
        model_id="vendor/embed",
        endpoint="https://openrouter.ai/api/v1/embeddings",
        credential_reference="OPENROUTER_API_KEY",
        dimensions=None,
        source=ConfigurationSource.PERSISTED,
    )

    with pytest.raises(ProviderConfigurationError, match="UNSUPPORTED_PROVIDER"):
        ProviderConfigurationResolver.validate(unsupported, store.providers())
    with pytest.raises(
        ProviderConfigurationError, match="EMBEDDING_DIMENSIONS_INVALID"
    ):
        ProviderConfigurationResolver.validate(invalid_embedding, store.providers())


def test_system_inspection_and_mutation_use_canonical_permissions() -> None:
    class Access:
        checked: list[tuple[UUID, Permission]] = []

        def require_system(self, actor: UUID, permission: Permission) -> None:
            self.checked.append((actor, permission))

    access = Access()
    store = Store()
    environment = fallback()
    service = ProviderConfigurationService(
        access=access,  # type: ignore[arg-type]
        resolver=ProviderConfigurationResolver(store=store, fallback=environment),
        store=store,
        fallback=environment,
    )

    snapshot = service.runtime_configuration(ACTOR)
    saved = service.configure(
        ACTOR,
        ModelCapability.GENERATION,
        provider="openrouter",
        model_id="vendor/persisted",
        endpoint="https://openrouter.ai/api/v1/chat/completions",
        credential_reference="OPENROUTER_API_KEY",
        dimensions=None,
        active=True,
    )

    assert access.checked == [
        (ACTOR, Permission.PROVIDERS_READ),
        (ACTOR, Permission.PROVIDERS_MANAGE),
    ]
    assert (
        snapshot["effective"]["generation"]["source"]  # type: ignore[index]
        == "ENVIRONMENT_FALLBACK"
    )
    assert saved["effective"]["source"] == "PERSISTED"  # type: ignore[index]
    assert "api_key_value" not in repr(snapshot).lower()


def test_execution_gateways_consume_resolver_before_server_side_credentials() -> None:
    bootstrap = read("src/knowledge_platform/bootstrap/application.py")
    model_gateway = bootstrap.split("def model_gateway", 1)[1].split(
        "def ingestion_service", 1
    )[0]
    embedding_gateway = bootstrap.split("def embedding_gateway", 1)[1].split(
        "def model_gateway", 1
    )[0]

    factory = read(
        "src/knowledge_platform/infrastructure/provider_configuration/factory.py"
    )

    assert "provider_adapter_factory().generation()" in model_gateway
    assert "provider_adapter_factory().embedding()" in embedding_gateway
    assert "self.settings.model_endpoint" not in model_gateway
    assert "self.settings.embedding_endpoint" not in embedding_gateway
    assert "self._resolver.resolve(ModelCapability.GENERATION)" in factory
    assert "self._resolver.resolve(ModelCapability.EMBEDDING)" in factory
    assert "CredentialReference(name=configuration.credential_reference)" in factory


def test_execution_adapter_factories_receive_canonical_resolved_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    credential_references: list[CredentialReference] = []

    class Resolver:
        def resolve(
            self, capability: ModelCapability
        ) -> ResolvedProviderConfiguration:
            if capability is ModelCapability.GENERATION:
                return ResolvedProviderConfiguration(
                    capability=capability,
                    provider="openrouter",
                    model_id="vendor/persisted-generation",
                    endpoint="https://configured.example/v1/chat",
                    credential_reference="GENERATION_KEY",
                    dimensions=None,
                    source=ConfigurationSource.PERSISTED,
                )
            return ResolvedProviderConfiguration(
                capability=capability,
                provider="openrouter",
                model_id="vendor/persisted-embedding",
                endpoint="https://configured.example/v1/embeddings",
                credential_reference="EMBEDDING_KEY",
                dimensions=768,
                source=ConfigurationSource.PERSISTED,
            )

    class Credentials:
        def resolve(self, reference: CredentialReference) -> str:
            credential_references.append(reference)
            return "test-only-secret"

    class ModelAdapter:
        def __init__(self, **values: object) -> None:
            captured["generation"] = values

    class EmbeddingAdapter:
        def __init__(self, **values: object) -> None:
            captured["embedding"] = values

    monkeypatch.setattr(
        "knowledge_platform.infrastructure.provider_configuration.factory.RemoteModelAdapter",
        ModelAdapter,
    )
    monkeypatch.setattr(
        "knowledge_platform.infrastructure.provider_configuration.factory.RemoteEmbeddingAdapter",
        EmbeddingAdapter,
    )
    factory = RemoteProviderAdapterFactory(
        resolver=Resolver(),  # type: ignore[arg-type]
        credentials=Credentials(),  # type: ignore[arg-type]
    )

    factory.generation()
    factory.embedding()

    assert captured["generation"] == {
        "endpoint": "https://configured.example/v1/chat",
        "model_reference": "vendor/persisted-generation",
        "api_key": "test-only-secret",
    }
    assert captured["embedding"] == {
        "endpoint": "https://configured.example/v1/embeddings",
        "model_reference": "vendor/persisted-embedding",
        "api_key": "test-only-secret",
        "dimensions": 768,
    }
    assert [value.name for value in credential_references] == [
        "GENERATION_KEY",
        "EMBEDDING_KEY",
    ]


def test_migration_is_global_revisioned_and_least_privilege() -> None:
    migration = read(
        "supabase/migrations/20260909173000_canonical_provider_model_resolution.sql"
    ).lower()

    assert "runtime_model_configuration_revisions" in migration
    assert "workspace_id" not in migration
    assert "capability in ('generation', 'embedding')" in migration
    assert "provider_code text not null references platform.provider_registry(code)" in migration
    assert "where is_current" in migration
    assert "security definer" in migration
    assert "set search_path = ''" in migration
    assert "user_has_system_permission('providers.manage')" in migration
    assert "revoke all on platform.runtime_model_configuration_revisions" in migration
    assert "grant update on platform.runtime_model_configuration_revisions" not in migration
    assert "grant insert on platform.runtime_model_configuration_revisions" not in migration
    assert "credential_value" not in migration
    assert "api_key" not in migration


def test_forward_migration_qualifies_runtime_configuration_update() -> None:
    migration = read(
        "supabase/migrations/20260909213308_fix_runtime_model_configuration_save.sql"
    ).lower()

    assert "create or replace function platform.save_runtime_model_configuration" in migration
    assert "update platform.runtime_model_configuration_revisions as previous_revision" in migration
    assert "where previous_revision.capability = requested_capability" in migration
    assert "and previous_revision.is_current" in migration
    assert "where capability = requested_capability" not in migration
    assert "user_has_system_permission('providers.manage')" in migration
    assert "security definer" in migration
    assert "set search_path = ''" in migration
    assert "revoke all on function platform.save_runtime_model_configuration" in migration
    assert "grant execute on function platform.save_runtime_model_configuration" in migration
    assert "grant update on platform.runtime_model_configuration_revisions" not in migration
    assert "grant insert on platform.runtime_model_configuration_revisions" not in migration


def test_system_api_and_ui_distinguish_all_configuration_sources() -> None:
    delivery = read("src/knowledge_platform/delivery/provider_configuration_api.py")
    security = read("src/knowledge_platform/delivery/security.py")
    providers = read("frontend/system/controls-pages.js").split(
        "export function providersPage", 1
    )[1].split("function providerEditor", 1)[0]

    assert '@router.get("/runtime")' in delivery
    assert '@router.put("/runtime/{capability}")' in delivery
    assert "Permission.PROVIDERS_MANAGE" in security
    assert "تهيئة التشغيل الفعالة" in providers
    assert "تهيئة التشغيل المحفوظة" in providers
    assert "بيئة التشغيل الاحتياطية" in providers
    assert "مراجع النماذج المحفوظة على المساعدين" in providers
    assert "لا تُستخدم لاختيار نموذج التنفيذ" in providers
    assert "/chat/completions" not in providers
    assert '"/embeddings"' not in providers
    assert "vector" not in providers.lower()


def test_workspace_and_assistant_metadata_do_not_control_global_runtime() -> None:
    bootstrap = read("src/knowledge_platform/bootstrap/application.py")
    resolver = bootstrap.split("def provider_configuration_resolver", 1)[1].split(
        "def provider_configuration", 1
    )[0]
    conversation = read("src/knowledge_platform/application/assistant_conversations.py")

    assert "workspace_provider_settings" not in resolver
    assert "assistant" not in resolver
    assert "assistant.model_configuration" not in conversation
