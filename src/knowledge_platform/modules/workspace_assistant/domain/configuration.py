"""Validated assistant configuration value objects."""

from dataclasses import dataclass

from ._validation import required_text


@dataclass(frozen=True, slots=True)
class ModelConfiguration:
    """Provider-independent model selection."""

    provider: str
    model_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", required_text(self.provider, field="provider"))
        object.__setattr__(
            self,
            "model_reference",
            required_text(self.model_reference, field="model_reference"),
        )


@dataclass(frozen=True, slots=True)
class RetrievalConfiguration:
    """The accepted default retrieval configuration with no tunable fields yet."""
