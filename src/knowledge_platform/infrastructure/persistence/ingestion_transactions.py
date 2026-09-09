"""Transaction runner for workspace-scoped ingestion operations."""

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.knowledge_ingestion import IngestionTransactionContext
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId

from ..vector_search.postgres import DocumentRepresentationRepository
from .repositories import KnowledgeSourceRepository
from .workspace_context import workspace_session_scope


class SqlAlchemyWorkspaceTransactionRunner:
    """Runs application callbacks in one workspace-scoped SQLAlchemy transaction."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def run(
        self,
        workspace_id: WorkspaceId,
        operation: Callable[[IngestionTransactionContext], Any],
    ) -> Any:
        with workspace_session_scope(self._factory, workspace_id) as session:
            context = IngestionTransactionContext(
                source_repository=KnowledgeSourceRepository(session),
                representation_repository=DocumentRepresentationRepository(session),
            )
            return operation(context)
