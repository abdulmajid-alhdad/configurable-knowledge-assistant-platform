"""SQLAlchemy persistence mappings for the Workspace and Assistant slice."""

from __future__ import annotations

from uuid import UUID

from pgvector.sqlalchemy import VECTOR
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


class AssistantKnowledgeSourceRecord(PlatformBase):
    """Workspace-scoped assistant/source authorization row."""

    __tablename__ = "assistant_knowledge_sources"
    __table_args__ = ({"schema": "platform"},)

    workspace_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    assistant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("platform.assistants.id"), primary_key=True
    )
    knowledge_source_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("platform.knowledge_sources.id"), primary_key=True
    )


class ConversationRecord(PlatformBase):
    """ORM record for ``platform.conversations``."""

    __tablename__ = "conversations"
    __table_args__ = ({"schema": "platform"},)

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("platform.workspaces.id"), nullable=False
    )
    assistant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("platform.assistants.id"), nullable=False
    )


class MessageRecord(PlatformBase):
    """ORM record for immutable conversation messages."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("sequence >= 0", name="messages_sequence_nonnegative"),
        CheckConstraint("role IN ('user', 'assistant')", name="messages_role_vocabulary"),
        CheckConstraint("btrim(content) <> ''", name="messages_content_nonblank"),
        {"schema": "platform"},
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("platform.conversations.id"),
        primary_key=True,
    )
    sequence: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentRepresentationRecord(PlatformBase):
    """ORM record for versioned retrieval representations."""

    __tablename__ = "document_representations"
    __table_args__ = (
        CheckConstraint("version > 0", name="document_representations_version_positive"),
        CheckConstraint("dimensions > 0", name="document_representations_dimensions_positive"),
        CheckConstraint(
            "state IN ('BUILDING', 'ACTIVE', 'RETIRED')",
            name="document_representations_state_vocabulary",
        ),
        {"schema": "retrieval"},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("platform.workspaces.id"),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("platform.knowledge_sources.id"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    embedding_profile: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[int] = mapped_column(nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)


class DocumentChunkRecord(PlatformBase):
    """ORM record for chunks and their pgvector embeddings."""

    __tablename__ = "document_chunks"
    __table_args__ = ({"schema": "retrieval"},)

    representation_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("retrieval.document_representations.id"),
        primary_key=True,
    )
    sequence: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_locator: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[object] = mapped_column(VECTOR(), nullable=False)
