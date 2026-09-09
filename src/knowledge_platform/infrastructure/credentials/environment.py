"""Environment-backed credential resolver for server-side adapter wiring."""

import os

from knowledge_platform.modules.workspace_assistant.domain.security import CredentialReference
from knowledge_platform.modules.workspace_assistant.ports.credentials import CredentialResolverPort


class EnvironmentCredentialResolver(CredentialResolverPort):
    """Resolve a logical credential reference from one environment variable."""

    def resolve(self, reference: CredentialReference) -> str:
        value = os.environ.get(reference.name)
        if value is None:
            raise RuntimeError(f"credential is unavailable for reference {reference.name}")
        normalized = value.strip()
        if not normalized:
            raise RuntimeError(f"credential is unavailable for reference {reference.name}")
        return normalized
