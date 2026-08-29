"""Outbound credential-resolution boundary."""

from typing import Protocol

from knowledge_platform.modules.workspace_assistant.domain.security import CredentialReference


class CredentialResolverPort(Protocol):
    """Resolve secret material only at the consuming boundary."""

    def resolve(self, reference: CredentialReference) -> str: ...
