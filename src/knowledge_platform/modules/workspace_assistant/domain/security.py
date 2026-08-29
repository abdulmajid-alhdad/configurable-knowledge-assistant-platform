"""Credential references and deterministic data-egress policy contracts."""

from dataclasses import dataclass
from enum import Enum

from ._validation import required_text


class PolicyDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"


class ProcessingLocation(Enum):
    LOCAL = "local"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class CredentialReference:
    """A logical credential name, never credential material."""

    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", required_text(self.name, field="name"))


@dataclass(frozen=True, slots=True)
class DataEgressPolicy:
    """Trusted policy state controlling private-data processing location."""

    external_private_data_allowed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.external_private_data_allowed, bool):
            raise TypeError("external_private_data_allowed must be a boolean")

    def decide(
        self,
        *,
        processing_location: ProcessingLocation,
        contains_private_data: bool,
    ) -> PolicyDecision:
        if not isinstance(processing_location, ProcessingLocation):
            raise TypeError("processing_location must be a ProcessingLocation")
        if not isinstance(contains_private_data, bool):
            raise TypeError("contains_private_data must be a boolean")
        if processing_location is ProcessingLocation.LOCAL:
            return PolicyDecision.ALLOW
        if not contains_private_data or self.external_private_data_allowed:
            return PolicyDecision.ALLOW
        return PolicyDecision.DENY
