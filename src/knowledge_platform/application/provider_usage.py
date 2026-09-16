"""Provider-owned usage telemetry application boundary."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.modules.access_control.domain import Permission


class ProviderUsageUnavailable(RuntimeError):
    """Provider telemetry could not be read without exposing provider details."""

    def __init__(self, category: str) -> None:
        super().__init__("provider usage telemetry unavailable")
        self.category = category


@dataclass(frozen=True, slots=True)
class ProviderUsageSource:
    """Safe provenance for provider telemetry, never credential material."""

    provider: str
    kind: str
    credential_reference: str | None


@dataclass(frozen=True, slots=True)
class ProviderUsageSummary:
    """Provider-authoritative usage values without local attribution."""

    provider: str
    retrieved_at: datetime
    currency: str
    usage: float | None
    usage_daily: float | None
    usage_weekly: float | None
    usage_monthly: float | None
    limit: float | None
    limit_remaining: float | None
    limit_reset: str | None
    is_free_tier: bool | None
    expires_at: str | None
    source: ProviderUsageSource


class ProviderUsagePort(Protocol):
    """Read normalized, non-secret provider telemetry."""

    def summary(self) -> ProviderUsageSummary: ...


class ProviderUsageControlPort(Protocol):
    def summary(self, actor: UUID) -> ProviderUsageSummary: ...


class ProviderUsageService:
    """Authorize SYSTEM usage reads before invoking the remote telemetry port."""

    def __init__(
        self,
        *,
        access: AccessControlPort,
        telemetry: ProviderUsagePort,
    ) -> None:
        self._access = access
        self._telemetry = telemetry

    def summary(self, actor: UUID) -> ProviderUsageSummary:
        self._access.require_system(actor, Permission.USAGE_READ)
        return self._telemetry.summary()
