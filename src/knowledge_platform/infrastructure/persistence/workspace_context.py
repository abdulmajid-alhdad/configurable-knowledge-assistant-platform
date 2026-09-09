"""Transaction-local trusted workspace context integration."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from knowledge_platform.application.security_context import current_user_id
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId

_NIL_WORKSPACE_ID = "00000000-0000-0000-0000-000000000000"


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
        user_id = current_user_id()
        if user_id is not None:
            session.execute(
                text("select set_config('app.user_id', :user_id, true)"),
                {"user_id": str(user_id)},
            )
        yield session


@contextmanager
def system_session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Bind only trusted user identity; a nil Workspace never grants scope."""
    with factory.begin() as session:
        session.execute(
            text("select set_config('app.workspace_id', :workspace_id, true)"),
            {"workspace_id": _NIL_WORKSPACE_ID},
        )
        user_id = current_user_id()
        if user_id is None:
            raise RuntimeError("system session requires an authenticated identity")
        session.execute(
            text("select set_config('app.user_id', :user_id, true)"),
            {"user_id": str(user_id)},
        )
        yield session
