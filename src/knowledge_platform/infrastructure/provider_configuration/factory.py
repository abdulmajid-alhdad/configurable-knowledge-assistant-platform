"""Construct remote execution adapters from canonical resolved configuration."""

from knowledge_platform.application.provider_configuration import (
    ModelCapability,
    ProviderConfigurationResolver,
)
from knowledge_platform.infrastructure.credentials.environment import (
    EnvironmentCredentialResolver,
)
from knowledge_platform.infrastructure.embeddings.remote import RemoteEmbeddingAdapter
from knowledge_platform.infrastructure.models.remote import RemoteModelAdapter
from knowledge_platform.modules.workspace_assistant.domain.security import (
    CredentialReference,
)


class RemoteProviderAdapterFactory:
    """Keep secret resolution inside the server-side adapter construction boundary."""

    def __init__(
        self,
        *,
        resolver: ProviderConfigurationResolver,
        credentials: EnvironmentCredentialResolver,
    ) -> None:
        self._resolver = resolver
        self._credentials = credentials

    def embedding(self) -> RemoteEmbeddingAdapter:
        configuration = self._resolver.resolve(ModelCapability.EMBEDDING)
        if configuration.dimensions is None:
            raise RuntimeError("canonical embedding dimensions are not configured")
        return RemoteEmbeddingAdapter(
            endpoint=configuration.endpoint,
            model_reference=configuration.model_id,
            api_key=self._credentials.resolve(
                CredentialReference(name=configuration.credential_reference)
            ),
            dimensions=configuration.dimensions,
        )

    def generation(self) -> RemoteModelAdapter:
        configuration = self._resolver.resolve(ModelCapability.GENERATION)
        return RemoteModelAdapter(
            endpoint=configuration.endpoint,
            model_reference=configuration.model_id,
            api_key=self._credentials.resolve(
                CredentialReference(name=configuration.credential_reference)
            ),
        )
