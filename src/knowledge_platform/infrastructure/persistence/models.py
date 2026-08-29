"""SQLAlchemy persistence mappings for the Workspace and Assistant slice."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PlatformBase(DeclarativeBase):
    """Base for platform persistence mappings only."""


class WorkspaceRecord(PlatformBase):
    """ORM record for ``platform.workspaces``."""

    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="workspaces_name_nonblank"),
        {"schema": "platform"},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class AssistantRecord(PlatformBase):
    """ORM record for ``platform.assistants``."""

    __tablename__ = "assistants"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="assistants_name_nonblank"),
        CheckConstraint("btrim(instructions) <> ''", name="assistants_instructions_nonblank"),
        CheckConstraint("btrim(language) <> ''", name="assistants_language_nonblank"),
        {"schema": "platform"},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("platform.workspaces.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    model_configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    retrieval_configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class KnowledgeSourceRecord(PlatformBase):
    """ORM record for ``platform.knowledge_sources``."""

    __tablename__ = "knowledge_sources"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="knowledge_sources_name_nonblank"),
        CheckConstraint(
            "kind IN ('document', 'structured')",
            name="knowledge_sources_kind_vocabulary",
        ),
        CheckConstraint(
            "lifecycle IN ("
            "'registered', 'preparing', 'ready', 'disabled', "
            "'failed', 'removing', 'removed'"
            ")",
            name="knowledge_sources_lifecycle_vocabulary",
        ),
        {"schema": "platform"},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("platform.workspaces.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle: Mapped[str] = mapped_column(Text, nullable=False)
