"""Contract coverage for the Stage 6B management API."""
# ruff: noqa: E501

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from knowledge_platform.delivery.product_api import create_management_router
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceKind
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace


class FakeServices:
    def __init__(self) -> None:
        self.workspace = Workspace.create(name="W1")
        self.assistants: list[Assistant] = []
        self.sources: list[KnowledgeSource] = []

    def create_workspace(self, name: str) -> Workspace:
        self.workspace = Workspace.create(name=name)
        return self.workspace

    def get_workspace(self, workspace_id):
        return self.workspace if workspace_id == self.workspace.id.value else None

    def create_assistant(self, workspace_id, payload):
        if workspace_id != self.workspace.id.value:
            raise LookupError
        value = Assistant.create(workspace_id=WorkspaceId(workspace_id), name=payload.name, description=payload.description, instructions=payload.instructions, language=payload.language, model_configuration=ModelConfiguration(provider=payload.provider, model_reference=payload.model_reference), retrieval_configuration=RetrievalConfiguration())
        self.assistants.append(value)
        return value

    def list_assistants(self, workspace_id):
        return [a for a in self.assistants if a.workspace_id.value == workspace_id]

    def get_assistant(self, workspace_id, assistant_id):
        return next((a for a in self.assistants if a.workspace_id.value == workspace_id and a.id.value == assistant_id), None)

    def update_assistant(self, workspace_id, assistant_id, payload):
        previous = self.get_assistant(workspace_id, assistant_id)
        if previous is None:
            raise LookupError
        value = previous.reconfigure(name=payload.name, description=payload.description, instructions=payload.instructions, language=payload.language, model_configuration=ModelConfiguration(provider=payload.provider, model_reference=payload.model_reference), retrieval_configuration=RetrievalConfiguration())
        self.assistants[self.assistants.index(previous)] = value
        return value

    def create_source(self, workspace_id, payload):
        if workspace_id != self.workspace.id.value:
            raise LookupError
        value = KnowledgeSource.create(workspace_id=WorkspaceId(workspace_id), name=payload.name, kind=KnowledgeSourceKind(payload.kind))
        self.sources.append(value)
        return value

    def list_sources(self, workspace_id):
        return [s for s in self.sources if s.workspace_id.value == workspace_id]

    def get_source(self, workspace_id, source_id):
        return next((s for s in self.sources if s.workspace_id.value == workspace_id and s.id.value == source_id), None)


@pytest.fixture
def client() -> TestClient:
    services = FakeServices()
    app = FastAPI()
    app.include_router(create_management_router(services))
    return TestClient(app)


def test_management_api_scopes_children_and_forbids_extra_fields(client: TestClient) -> None:
    workspace = client.post("/api/workspaces", json={"name": "demo"}).json()
    wid = workspace["id"]
    payload = {"name": "assistant", "instructions": "answer", "language": "en", "provider": "remote", "model_reference": "m"}
    created = client.post(f"/api/workspaces/{wid}/assistants", json=payload)
    assert created.status_code == 201
    assert client.get(f"/api/workspaces/{wid}/assistants").json()[0]["workspace_id"] == wid
    assert client.post("/api/workspaces", json={"name": "x", "secret": "no"}).status_code == 422


def test_source_registration_does_not_accept_lifecycle(client: TestClient) -> None:
    wid = client.post("/api/workspaces", json={"name": "demo"}).json()["id"]
    response = client.post(f"/api/workspaces/{wid}/sources", json={"name": "docs", "kind": "document", "lifecycle": "ready"})
    assert response.status_code == 422
