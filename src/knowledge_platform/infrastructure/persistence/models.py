"""SQLAlchemy persistence mappings for the Workspace and Assistant slice."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Text
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
        CheckConstraint(
            "operational_status IN ('ACTIVE', 'SUSPENDED')",
            name="workspaces_operational_status_vocabulary",
        ),
        CheckConstraint(
            "operational_status <> 'SUSPENDED' OR NOT ai_execution_enabled",
            name="workspaces_suspended_disables_ai",
        ),
        {"schema": "platform"},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    operational_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="ACTIVE"
    )
    ai_execution_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )


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
    __table_args__ = (
        CheckConstraint("btrim(title) <> ''", name="conversations_title_nonblank"),
        CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name="conversations_status_vocabulary",
        ),
        CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) OR "
            "(status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="conversations_archive_state_consistent",
        ),
        {"schema": "platform"},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("platform.workspaces.id"), nullable=False
    )
    assistant_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("platform.assistants.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MessageRecord(PlatformBase):
    """ORM record for immutable conversation messages."""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("sequence >= 0", name="messages_sequence_nonnegative"),
        CheckConstraint("role IN ('user', 'assistant')", name="messages_role_vocabulary"),
        CheckConstraint("btrim(content) <> ''", name="messages_content_nonblank"),
        CheckConstraint(
            "outcome IS NULL OR outcome IN "
            "('grounded', 'insufficient_evidence', 'policy_denied', 'technical_failure')",
            name="messages_outcome_vocabulary",
        ),
        CheckConstraint(
            "outcome IS NULL OR role = 'assistant'",
            name="messages_assistant_outcome_only",
        ),
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
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)


class MessageEvidenceRecord(PlatformBase):
    """Ordered evidence snapshot cited by one persisted assistant message."""

    __tablename__ = "message_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_id", "message_sequence"],
            ["platform.messages.conversation_id", "platform.messages.sequence"],
        ),
        CheckConstraint("ordinal > 0", name="message_evidence_ordinal_positive"),
        CheckConstraint("btrim(content) <> ''", name="message_evidence_content_nonblank"),
        CheckConstraint(
            "btrim(provenance_locator) <> ''",
            name="message_evidence_provenance_nonblank",
        ),
        {"schema": "platform"},
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True
    )
    message_sequence: Mapped[int] = mapped_column(primary_key=True)
    ordinal: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("platform.knowledge_sources.id"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_locator: Mapped[str] = mapped_column(Text, nullable=False)


class SystemConversationRecord(PlatformBase):
    """System-scoped administrative conversation; never a Workspace row."""

    __tablename__ = "system_conversations"
    __table_args__ = (
        CheckConstraint("btrim(title) <> ''", name="system_conversations_title_nonblank"),
        CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name="system_conversations_status_vocabulary",
        ),
        {"schema": "platform"},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")
    created_by: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SystemConversationMessageRecord(PlatformBase):
    """Append-only message belonging to a System conversation."""

    __tablename__ = "system_conversation_messages"
    __table_args__ = (
        CheckConstraint(
            "sequence >= 0", name="system_conversation_messages_sequence_nonnegative"
        ),
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="system_conversation_messages_role_vocabulary",
        ),
        CheckConstraint(
            "btrim(content) <> ''",
            name="system_conversation_messages_content_nonblank",
        ),
        {"schema": "platform"},
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("platform.system_conversations.id"),
        primary_key=True,
    )
    sequence: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
