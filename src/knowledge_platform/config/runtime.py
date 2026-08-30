"""Environment-backed production runtime configuration."""

from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from knowledge_platform.modules.workspace_assistant.domain.security import (
    CredentialReference,
)


class RuntimeSettings(BaseSettings):
    """Validated settings for the production composition root."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        hide_input_in_errors=True,
    )

    mode: Literal["production", "deterministic"] = Field(
        default="production", validation_alias="KNOWLEDGE_PLATFORM_MODE"
    )
    database_dsn: SecretStr | None = Field(
        default=None, validation_alias="PLATFORM_DATABASE_DSN", repr=False
    )
    embedding_endpoint: str | None = Field(
        default=None, validation_alias="EMBEDDING_ENDPOINT"
    )
    embedding_model: str | None = Field(
        default=None, validation_alias="EMBEDDING_MODEL_REFERENCE"
    )
    embedding_credential: str | None = Field(
        default=None, validation_alias="EMBEDDING_CREDENTIAL_REFERENCE"
    )
    embedding_dimensions: int | None = Field(
        default=None, validation_alias="EMBEDDING_DIMENSIONS"
    )
    model_endpoint: str | None = Field(default=None, validation_alias="MODEL_ENDPOINT")
    model_reference: str | None = Field(
        default=None, validation_alias="MODEL_REFERENCE"
    )
    model_credential: str | None = Field(
        default=None, validation_alias="MODEL_CREDENTIAL_REFERENCE"
    )
    external_private_data_allowed: bool = Field(
        default=False, validation_alias="EXTERNAL_PRIVATE_DATA_ALLOWED"
    )
    artifact_root: str = Field(
        default="/var/lib/knowledge-platform/artifacts",
        validation_alias="KNOWLEDGE_ARTIFACT_ROOT",
    )
    max_artifact_bytes: int = Field(
        default=10_000_000, validation_alias="KNOWLEDGE_MAX_ARTIFACT_BYTES"
    )

    @field_validator(
        "embedding_endpoint",
        "embedding_model",
        "embedding_credential",
        "model_endpoint",
        "model_reference",
        "model_credential",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("provider configuration must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def validate_production_requirements(self) -> "RuntimeSettings":
        if self.mode == "production":
            required = (
                self.database_dsn,
                self.embedding_endpoint,
                self.embedding_model,
                self.embedding_credential,
                self.embedding_dimensions,
                self.model_endpoint,
                self.model_reference,
                self.model_credential,
            )
            if any(value is None for value in required):
                raise ValueError("production provider configuration is incomplete")
        return self

    @property
    def credential_for_embedding(self) -> CredentialReference:
        if self.embedding_credential is None:
            raise ValueError("embedding credential reference is not configured")
        return CredentialReference(name=self.embedding_credential)

    @property
    def credential_for_model(self) -> CredentialReference:
        if self.model_credential is None:
            raise ValueError("model credential reference is not configured")
        return CredentialReference(name=self.model_credential)
