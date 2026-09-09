"""Provider-owned usage telemetry application boundary."""

from typing import Protocol
from uuid import UUID

from knowledge_platform.application.access_control import AccessControlPort
from knowledge_platform.modules.access_control.domain import Permission


class ProviderUsageUnavailable(RuntimeError):
    """Provider telemetry could not be read without exposing provider details."""

    def __init__(self, category: str) -> None:
        super().__init__("provider usage telemetry unavailable")
        self.category = category


class ProviderUsagePort(Protocol):
    """Read normalized, non-secret provider telemetry."""

    def summary(self) -> dict[str, object]: ...


class ProviderUsageControlPort(Protocol):
    def summary(self, actor: UUID) -> dict[str, object]: ...


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

    def summary(self, actor: UUID) -> dict[str, object]:
        self._access.require_system(actor, Permission.USAGE_READ)
        return self._telemetry.summary()
