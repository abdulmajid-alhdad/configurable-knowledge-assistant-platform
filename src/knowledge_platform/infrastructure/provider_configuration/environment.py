"""Environment bootstrap/fallback for remote provider configuration."""

from urllib.parse import urlsplit

from knowledge_platform.application.provider_configuration import (
    ConfigurationSource,
    ModelCapability,
    ResolvedProviderConfiguration,
)


class EnvironmentProviderConfiguration:
    """Expose an atomic fallback without resolving credential values."""

    def __init__(
        self,
        *,
        generation_endpoint: str | None,
        generation_model: str | None,
        generation_credential_reference: str | None,
        embedding_endpoint: str | None,
        embedding_model: str | None,
        embedding_credential_reference: str | None,
        embedding_dimensions: int | None,
    ) -> None:
        generation_ready = all(
            (generation_endpoint, generation_model, generation_credential_reference)
        )
        embedding_ready = all(
            (
                embedding_endpoint,
                embedding_model,
                embedding_credential_reference,
                embedding_dimensions,
            )
        )
        self._values = {
            ModelCapability.GENERATION: ResolvedProviderConfiguration(
                capability=ModelCapability.GENERATION,
                provider=self._provider_for(generation_endpoint),
                model_id=generation_model or "",
                endpoint=generation_endpoint or "",
                credential_reference=generation_credential_reference or "",
                dimensions=None,
                source=ConfigurationSource.ENVIRONMENT_FALLBACK,
                structurally_ready=generation_ready,
            ),
            ModelCapability.EMBEDDING: ResolvedProviderConfiguration(
                capability=ModelCapability.EMBEDDING,
                provider=self._provider_for(embedding_endpoint),
                model_id=embedding_model or "",
                endpoint=embedding_endpoint or "",
                credential_reference=embedding_credential_reference or "",
                dimensions=embedding_dimensions,
                source=ConfigurationSource.ENVIRONMENT_FALLBACK,
                structurally_ready=embedding_ready,
            ),
        }

    @staticmethod
    def _provider_for(endpoint: str | None) -> str:
        hostname = (urlsplit(endpoint or "").hostname or "").lower()
        return "openrouter" if hostname == "openrouter.ai" else "remote"

    def configuration(
        self, capability: ModelCapability
    ) -> ResolvedProviderConfiguration:
        return self._values[capability]
