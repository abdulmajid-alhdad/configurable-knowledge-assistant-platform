"""SYSTEM-authorized, provider-neutral remote model catalogue contracts."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Protocol
from uuid import UUID

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.application.provider_configuration import (
    ModelCapability,
    ProviderConfigurationStorePort,
)
from knowledge_platform.modules.access_control.domain import Permission


class ProviderModelCatalogueError(RuntimeError):
    """A safe, bounded provider catalogue failure."""


@dataclass(frozen=True, slots=True)
class ModelCatalogueEntry:
    provider: str
    model_id: str
    display_name: str
    capability: ModelCapability
    context_length: int | None
    input_modalities: tuple[str, ...]
    output_modalities: tuple[str, ...]
    embedding_dimensions: int | None = None
    description: str | None = None


class ProviderModelCataloguePort(Protocol):
    def models(
        self, capability: ModelCapability
    ) -> tuple[ModelCatalogueEntry, ...]: ...


class ProviderModelCatalogueControlPort(Protocol):
    def models(
        self,
        actor: UUID,
        provider: str,
        capability: ModelCapability,
    ) -> dict[str, object]: ...


class ProviderModelCatalogueService:
    """Authorize provider-neutral catalogue discovery and sanitize its response."""

    def __init__(
        self,
        *,
        access: AccessControlPort,
        providers: ProviderConfigurationStorePort,
        catalogues: Mapping[str, ProviderModelCataloguePort],
    ) -> None:
        self._access = access
        self._providers = providers
        self._catalogues = catalogues

    def models(
        self,
        actor: UUID,
        provider: str,
        capability: ModelCapability,
    ) -> dict[str, object]:
        self._access.require_system(actor, Permission.PROVIDERS_READ)
        provider_code = provider.strip().lower()
        definition = next(
            (item for item in self._providers.providers() if item.code == provider_code),
            None,
        )
        if definition is None:
            raise ProviderModelCatalogueError("UNSUPPORTED_PROVIDER")
        supported_types = {
            ModelCapability.GENERATION: {"generation", "multi"},
            ModelCapability.EMBEDDING: {"embeddings", "multi"},
        }[capability]
        if definition.provider_type not in supported_types:
            raise ProviderModelCatalogueError("PROVIDER_CAPABILITY_MISMATCH")
        catalogue = self._catalogues.get(provider_code)
        if catalogue is None:
            raise ProviderModelCatalogueError("CATALOGUE_INTEGRATION_UNAVAILABLE")
        entries = catalogue.models(capability)
        if any(
            entry.provider != provider_code or entry.capability is not capability
            for entry in entries
        ):
            raise ProviderModelCatalogueError("CATALOGUE_RESPONSE_INVALID")
        models: list[dict[str, object]] = []
        for entry in entries:
            value = asdict(entry)
            value["capability"] = entry.capability.value
            models.append(value)
        return {
            "provider": provider_code,
            "capability": capability.value,
            "models": models,
        }
