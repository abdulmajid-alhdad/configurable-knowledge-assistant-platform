"""Least-privilege SQL adapter for global runtime model configuration."""

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.provider_configuration import (
    ModelCapability,
    ProviderConfigurationInput,
    ProviderDefinition,
    StoredProviderConfiguration,
)
from knowledge_platform.infrastructure.persistence.workspace_context import (
    system_session_scope,
)


class SqlAlchemyProviderConfigurationStore:
    """Use protected functions; the runtime role has no table mutation grant."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @staticmethod
    def _configuration(row: RowMapping) -> StoredProviderConfiguration:
        return StoredProviderConfiguration(
            id=cast(UUID, row["id"]),
            capability=ModelCapability(cast(str, row["capability"])),
            provider=cast(str, row["provider_code"]),
            model_id=cast(str, row["model_identifier"]),
            endpoint=cast(str, row["endpoint"]),
            credential_reference=cast(str, row["credential_reference"]),
            dimensions=cast(int | None, row["embedding_dimensions"]),
            active=cast(bool, row["active"]),
            created_by=cast(UUID, row["created_by"]),
            created_at=cast(datetime, row["created_at"]),
        )

    def configuration(
        self, capability: ModelCapability
    ) -> StoredProviderConfiguration | None:
        with self._sessions.begin() as session:
            row = session.execute(
                text(
                    "select * from platform.get_runtime_model_configuration(:capability)"
                ),
                {"capability": capability.value},
            ).mappings().one_or_none()
        return None if row is None else self._configuration(row)

    def providers(self) -> tuple[ProviderDefinition, ...]:
        with self._sessions.begin() as session:
            rows = session.execute(
                text("select * from platform.list_runtime_provider_catalogue()")
            ).mappings().all()
        return tuple(
            ProviderDefinition(
                code=cast(str, row["code"]),
                display_name=cast(str, row["display_name"]),
                provider_type=cast(str, row["provider_type"]),
                base_url=cast(str | None, row["base_url"]),
            )
            for row in rows
        )

    def save(
        self,
        actor: UUID,
        value: ProviderConfigurationInput,
        request_id: str | None,
    ) -> StoredProviderConfiguration:
        del actor  # Identity is bound by system_session_scope/current_user_id.
        with system_session_scope(self._sessions) as session:
            row = session.execute(
                text("""
                    select * from platform.save_runtime_model_configuration(
                      :capability,:provider,:model,:endpoint,:credential,
                      :dimensions,:active,:request_id)
                """),
                {
                    "capability": value.capability.value,
                    "provider": value.provider,
                    "model": value.model_id,
                    "endpoint": value.endpoint,
                    "credential": value.credential_reference,
                    "dimensions": value.dimensions,
                    "active": value.active,
                    "request_id": request_id,
                },
            ).mappings().one()
        return self._configuration(cast(RowMapping, row))
