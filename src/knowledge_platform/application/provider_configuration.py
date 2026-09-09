"""Canonical, SYSTEM-controlled provider/model configuration resolution."""

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.modules.access_control.domain import Permission


class ModelCapability(StrEnum):
    GENERATION = "generation"
    EMBEDDING = "embedding"


class ConfigurationSource(StrEnum):
    PERSISTED = "PERSISTED"
    ENVIRONMENT_FALLBACK = "ENVIRONMENT_FALLBACK"


class ProviderConfigurationError(RuntimeError):
    """A structurally invalid effective configuration must fail closed."""


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    code: str
    display_name: str
    provider_type: str
    base_url: str | None


@dataclass(frozen=True, slots=True)
class StoredProviderConfiguration:
    id: UUID
    capability: ModelCapability
    provider: str
    model_id: str
    endpoint: str
    credential_reference: str
    dimensions: int | None
    active: bool
    created_by: UUID
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ResolvedProviderConfiguration:
    capability: ModelCapability
    provider: str
    model_id: str
    endpoint: str
    credential_reference: str
    dimensions: int | None
    source: ConfigurationSource
    scope: str = "GLOBAL"
    structurally_ready: bool = True


@dataclass(frozen=True, slots=True)
class ProviderConfigurationInput:
    capability: ModelCapability
    provider: str
    model_id: str
    endpoint: str
    credential_reference: str
    dimensions: int | None
    active: bool


class EnvironmentProviderConfigurationPort(Protocol):
    def configuration(
        self, capability: ModelCapability
    ) -> ResolvedProviderConfiguration: ...


class ProviderConfigurationStorePort(Protocol):
    def configuration(
        self, capability: ModelCapability
    ) -> StoredProviderConfiguration | None: ...

    def providers(self) -> tuple[ProviderDefinition, ...]: ...

    def save(
        self,
        actor: UUID,
        value: ProviderConfigurationInput,
        request_id: str | None,
    ) -> StoredProviderConfiguration: ...


class ProviderConfigurationControlPort(Protocol):
    def runtime_configuration(self, actor: UUID) -> dict[str, object]: ...

    def configure(
        self,
        actor: UUID,
        capability: ModelCapability,
        *,
        provider: str,
        model_id: str,
        endpoint: str,
        credential_reference: str,
        dimensions: int | None,
        active: bool,
        request_id: str | None = None,
    ) -> dict[str, object]: ...


_CREDENTIAL_REFERENCE = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")


class ProviderConfigurationResolver:
    """Resolve one atomic configuration source for each model capability."""

    def __init__(
        self,
        *,
        store: ProviderConfigurationStorePort,
        fallback: EnvironmentProviderConfigurationPort,
    ) -> None:
        self._store = store
        self._fallback = fallback

    def resolve(
        self, capability: ModelCapability
    ) -> ResolvedProviderConfiguration:
        persisted = self._store.configuration(capability)
        if persisted is not None and persisted.active:
            resolved = ResolvedProviderConfiguration(
                capability=capability,
                provider=persisted.provider,
                model_id=persisted.model_id,
                endpoint=persisted.endpoint,
                credential_reference=persisted.credential_reference,
                dimensions=persisted.dimensions,
                source=ConfigurationSource.PERSISTED,
            )
            self.validate(resolved, self._store.providers())
            return resolved

        fallback = self._fallback.configuration(capability)
        if not fallback.structurally_ready:
            raise ProviderConfigurationError("ENVIRONMENT_FALLBACK_INCOMPLETE")
        self.validate(fallback, self._store.providers())
        return fallback

    @staticmethod
    def validate(
        value: ResolvedProviderConfiguration | ProviderConfigurationInput,
        providers: tuple[ProviderDefinition, ...],
    ) -> None:
        provider = next((item for item in providers if item.code == value.provider), None)
        if provider is None:
            raise ProviderConfigurationError("UNSUPPORTED_PROVIDER")
        supported_types = {
            ModelCapability.GENERATION: {"generation", "multi"},
            ModelCapability.EMBEDDING: {"embeddings", "multi"},
        }[value.capability]
        if provider.provider_type not in supported_types:
            raise ProviderConfigurationError("PROVIDER_CAPABILITY_MISMATCH")
        if not value.model_id.strip():
            raise ProviderConfigurationError("MODEL_IDENTIFIER_REQUIRED")
        endpoint = urlsplit(value.endpoint)
        if endpoint.scheme != "https" or not endpoint.netloc:
            raise ProviderConfigurationError("REMOTE_HTTPS_ENDPOINT_REQUIRED")
        if not _CREDENTIAL_REFERENCE.fullmatch(value.credential_reference):
            raise ProviderConfigurationError("CREDENTIAL_REFERENCE_INVALID")
        if value.capability is ModelCapability.EMBEDDING:
            if value.dimensions is None or value.dimensions <= 0:
                raise ProviderConfigurationError("EMBEDDING_DIMENSIONS_INVALID")
        elif value.dimensions is not None:
            raise ProviderConfigurationError("GENERATION_DIMENSIONS_UNSUPPORTED")


class ProviderConfigurationService:
    """Authorize inspection/mutation while sharing the execution resolver."""

    def __init__(
        self,
        *,
        access: AccessControlPort,
        resolver: ProviderConfigurationResolver,
        store: ProviderConfigurationStorePort,
        fallback: EnvironmentProviderConfigurationPort,
    ) -> None:
        self._access = access
        self._resolver = resolver
        self._store = store
        self._fallback = fallback

    @staticmethod
    def _resolved(value: ResolvedProviderConfiguration) -> dict[str, object]:
        result = asdict(value)
        result["capability"] = value.capability.value
        result["source"] = value.source.value
        return result

    @staticmethod
    def _stored(
        value: StoredProviderConfiguration | None,
    ) -> dict[str, object] | None:
        if value is None:
            return None
        result = asdict(value)
        result["id"] = str(value.id)
        result["created_by"] = str(value.created_by)
        result["capability"] = value.capability.value
        return result

    @staticmethod
    def _provider(value: ProviderDefinition) -> dict[str, object]:
        return asdict(value)

    def runtime_configuration(self, actor: UUID) -> dict[str, object]:
        self._access.require_system(actor, Permission.PROVIDERS_READ)
        persisted = {
            capability.value: self._store.configuration(capability)
            for capability in ModelCapability
        }
        fallback = {
            capability.value: self._fallback.configuration(capability)
            for capability in ModelCapability
        }
        effective = {
            capability.value: self._resolver.resolve(capability)
            for capability in ModelCapability
        }
        return {
            "scope": "GLOBAL",
            "connectivity_verified": False,
            "effective": {
                key: self._resolved(value) for key, value in effective.items()
            },
            "persisted": {
                key: self._stored(value) for key, value in persisted.items()
            },
            "environment_fallback": {
                key: self._resolved(value) for key, value in fallback.items()
            },
            "providers": [self._provider(value) for value in self._store.providers()],
        }

    def configure(
        self,
        actor: UUID,
        capability: ModelCapability,
        *,
        provider: str,
        model_id: str,
        endpoint: str,
        credential_reference: str,
        dimensions: int | None,
        active: bool,
        request_id: str | None = None,
    ) -> dict[str, object]:
        self._access.require_system(actor, Permission.PROVIDERS_MANAGE)
        value = ProviderConfigurationInput(
            capability=capability,
            provider=provider.strip(),
            model_id=model_id.strip(),
            endpoint=endpoint.strip(),
            credential_reference=credential_reference.strip(),
            dimensions=dimensions,
            active=active,
        )
        ProviderConfigurationResolver.validate(value, self._store.providers())
        saved = self._store.save(actor, value, request_id)
        effective = self._resolver.resolve(capability)
        return {
            "persisted": self._stored(saved),
            "effective": self._resolved(effective),
        }
