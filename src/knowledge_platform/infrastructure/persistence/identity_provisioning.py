"""SQLAlchemy persistence adapter for activation-only provisioning intent."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.access_control import AccessConflict
from knowledge_platform.application.identity_provisioning import (
    ActivationPreview,
    ActivationResult,
    ProvisionedIdentity,
    ProvisioningIntent,
)


class SqlAlchemyIdentityProvisioningStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @contextmanager
    def _tx(
        self, user_id: UUID | None = None, workspace_id: UUID | None = None
    ) -> Iterator[Session]:
        with self._sessions.begin() as session:
            session.execute(
                text("select set_config('app.user_id', :value, true)"),
                {"value": str(user_id or UUID(int=0))},
            )
            session.execute(
                text("select set_config('app.workspace_id', :value, true)"),
                {"value": str(workspace_id or UUID(int=0))},
            )
            yield session

    def validate(self, actor: UUID, intent: ProvisioningIntent) -> None:
        with self._tx(actor, intent.workspace_id) as session:
            denial = session.execute(
                text(
                    "select platform.validate_identity_provisioning("
                    ":workspace,:email,:role,:team,:expires)"
                ),
                {
                    "workspace": intent.workspace_id,
                    "email": intent.email,
                    "role": intent.role_id,
                    "team": intent.team_id,
                    "expires": intent.expires_at,
                },
            ).scalar_one()
        if denial is not None:
            raise AccessConflict(str(denial))

    def create(
        self,
        actor: UUID,
        identity: ProvisionedIdentity,
        intent: ProvisioningIntent,
        token_digest: str,
    ) -> dict[str, object]:
        with self._tx(actor, intent.workspace_id) as session:
            row = session.execute(
                text(
                    "select * from platform.create_identity_provisioning_invitation("
                    ":workspace,:user,:email,:display_name,:role,:team,:digest,:expires)"
                ),
                {
                    "workspace": intent.workspace_id,
                    "user": identity.id,
                    "email": intent.email,
                    "display_name": intent.display_name,
                    "role": intent.role_id,
                    "team": intent.team_id,
                    "digest": token_digest,
                    "expires": intent.expires_at,
                },
            ).mappings().one()
            return dict(row)

    def preview(self, token_digest: str) -> ActivationPreview:
        with self._tx() as session:
            row = session.execute(
                text("select * from platform.preview_identity_activation(:digest)"),
                {"digest": token_digest},
            ).mappings().one()
            return ActivationPreview(
                invitation_id=cast(UUID | None, row["invitation_id"]),
                provisioned_user_id=cast(UUID | None, row["provisioned_user_id"]),
                email=cast(str | None, row["email"]),
                display_name=cast(str | None, row["display_name"]),
                workspace_id=cast(UUID | None, row["workspace_id"]),
                workspace_name=cast(str | None, row["workspace_name"]),
                role_id=cast(UUID | None, row["role_id"]),
                role_name=cast(str | None, row["role_name"]),
                team_id=cast(UUID | None, row["team_id"]),
                team_name=cast(str | None, row["team_name"]),
                status=cast(str | None, row["invitation_status"]),
                expires_at=cast(datetime | None, row["expires_at"]),
                error_code=cast(str | None, row["error_code"]),
            )

    def activate(self, token_digest: str, user_id: UUID) -> ActivationResult:
        with self._tx() as session:
            row = session.execute(
                text(
                    "select * from platform.activate_identity_provisioning("
                    ":digest,:user)"
                ),
                {"digest": token_digest, "user": user_id},
            ).mappings().one()
            return ActivationResult(
                workspace_id=cast(UUID | None, row["activated_workspace_id"]),
                user_id=cast(UUID | None, row["activated_user_id"]),
                team_id=cast(UUID | None, row["activated_team_id"]),
                error_code=cast(str | None, row["error_code"]),
            )
