"""Validated JSON payloads for persistence configuration value objects."""

from pydantic import BaseModel, ConfigDict, field_validator


class ModelConfigurationPayload(BaseModel):
    """Schema-bounded persisted representation of ModelConfiguration."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model_reference: str

    @field_validator("provider", "model_reference")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("configuration text must not be blank")
        return normalized


class RetrievalConfigurationPayload(BaseModel):
    """Currently empty, schema-bounded persisted retrieval configuration."""

    model_config = ConfigDict(extra="forbid")
