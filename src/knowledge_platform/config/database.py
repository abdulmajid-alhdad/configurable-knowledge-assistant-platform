"""Validated configuration for the platform-owned PostgreSQL database."""

from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PlatformDatabaseSettings(BaseSettings):
    """Environment-backed platform database connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="",
        extra="ignore",
        hide_input_in_errors=True,
    )

    platform_database_dsn: SecretStr = Field(
        validation_alias="PLATFORM_DATABASE_DSN",
        repr=False,
    )

    @field_validator("platform_database_dsn", mode="before")
    @classmethod
    def validate_dsn(cls, value: object) -> object:
        if not isinstance(value, str):
            raise TypeError("PLATFORM_DATABASE_DSN must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("PLATFORM_DATABASE_DSN must not be blank")
        if urlsplit(normalized).scheme != "postgresql+psycopg":
            raise ValueError("PLATFORM_DATABASE_DSN must use postgresql+psycopg")
        return normalized

    @property
    def dsn(self) -> str:
        """Return the DSN for infrastructure consumers without exposing it in repr."""
        return self.platform_database_dsn.get_secret_value()
