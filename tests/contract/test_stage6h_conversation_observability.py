"""Safe diagnostics for persisted conversation ask failures."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from knowledge_platform.delivery.conversation_api import create_conversation_router


class _FailingConversationServices:
    def create_conversation(self, workspace_id: UUID, assistant_id: UUID) -> Any:
        raise NotImplementedError

    def get_conversation(self, workspace_id: UUID, conversation_id: UUID) -> Any:
        return None

    def ask_conversation(self, workspace_id: UUID, conversation_id: UUID, question: str) -> object:
        raise RuntimeError(
            "SECRET_QUESTION SECRET_RETRIEVED_CHUNK SECRET_PROMPT "
            "SECRET_TOKEN SECRET_SQL_PARAMETER"
        )


def test_ask_failure_preserves_http_contract_and_sanitizes_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    app.include_router(create_conversation_router(_FailingConversationServices()))
    client = TestClient(app)
    workspace_id, conversation_id = uuid4(), uuid4()

    with caplog.at_level("ERROR", logger="knowledge_platform.delivery.conversation_api"):
        response = client.post(
            f"/api/workspaces/{workspace_id}/conversations/{conversation_id}/ask",
            json={"question": "SECRET_QUESTION"},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "request could not be completed"}
    record = next(
        item
        for item in caplog.records
        if item.getMessage().startswith("conversation_ask_failed")
    )
    assert record.workspace_id == str(workspace_id)
    assert record.conversation_id == str(conversation_id)
    assert record.exception_type == "RuntimeError"
    assert record.exc_info is not None
    for secret in (
        "SECRET_QUESTION",
        "SECRET_RETRIEVED_CHUNK",
        "SECRET_PROMPT",
        "SECRET_TOKEN",
        "SECRET_SQL_PARAMETER",
    ):
        assert secret not in caplog.text


def test_ask_failure_logs_only_structured_database_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Diagnostics:
        sqlstate = "23505"
        constraint_name = "messages_pkey"
        table_name = "messages"
        schema_name = "platform"

    class DatabaseError(RuntimeError):
        diag = Diagnostics()
        orig = None

    class Services(_FailingConversationServices):
        def ask_conversation(self, workspace_id: UUID, conversation_id: UUID, question: str) -> object:
            raise DatabaseError(
                "SECRET_SQL_PARAMETER SECRET_QUESTION SECRET_TOKEN"
            )

    app = FastAPI()
    app.include_router(create_conversation_router(Services()))
    client = TestClient(app)
    workspace_id, conversation_id = uuid4(), uuid4()

    with caplog.at_level("ERROR", logger="knowledge_platform.delivery.conversation_api"):
        response = client.post(
            f"/api/workspaces/{workspace_id}/conversations/{conversation_id}/ask",
            json={"question": "SECRET_QUESTION"},
        )

    assert response.status_code == 500
    record = next(
        item
        for item in caplog.records
        if item.getMessage().startswith("conversation_ask_failed")
    )
    assert record.sqlstate == "23505"
    assert record.constraint_name == "messages_pkey"
    assert record.table_name == "messages"
    assert record.schema_name == "platform"
    assert "sqlstate=23505" in caplog.text
    assert "constraint_name=messages_pkey" in caplog.text
    assert "table_name=messages" in caplog.text
    assert "schema_name=platform" in caplog.text
    assert "SECRET_SQL_PARAMETER" not in caplog.text
    assert "SECRET_QUESTION" not in caplog.text
    assert "SECRET_TOKEN" not in caplog.text
