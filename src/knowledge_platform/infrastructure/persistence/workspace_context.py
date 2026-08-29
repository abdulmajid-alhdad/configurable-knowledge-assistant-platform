"""Transaction-local trusted workspace context integration."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


def set_workspace_context(session: Session, workspace_id: WorkspaceId) -> None:
    """Set the trusted workspace context for the current transaction only."""
    session.execute(
        text("select set_config('app.workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace_id)},
    )


@contextmanager
def workspace_session_scope(
    factory: sessionmaker[Session], workspace_id: WorkspaceId
) -> Iterator[Session]:
    """Set workspace context and yield the same session within one transaction."""
    with factory.begin() as session:
        set_workspace_context(session, workspace_id)
        yield session
