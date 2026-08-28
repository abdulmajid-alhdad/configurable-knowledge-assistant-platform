"""Knowledge source kind and administrative lifecycle values."""

from enum import StrEnum


class KnowledgeSourceKind(StrEnum):
    """The source kinds currently supported by the domain contract."""

    DOCUMENT = "document"
    STRUCTURED = "structured"


class KnowledgeSourceLifecycle(StrEnum):
    """Administrative lifecycle of a registered knowledge source."""

    REGISTERED = "registered"
    PREPARING = "preparing"
    READY = "ready"
    DISABLED = "disabled"
    FAILED = "failed"
    REMOVING = "removing"
    REMOVED = "removed"
