"""Contract tests for persisted assistant/source scope semantics."""
# ruff: noqa: E501

from uuid import uuid4

import pytest

from knowledge_platform.application.assistant_knowledge_scope import AssistantKnowledgeScopeService
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceKind
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import WorkspaceId


class Repo:
    def __init__(self, assistant: Assistant, source: KnowledgeSource) -> None:
        self.assistant, self.source = assistant, source
        self.links: set[KnowledgeSourceId] = set()

    def get(self, *, workspace_id, assistant_id=None, source_id=None):
        if assistant_id is not None:
            return self.assistant if assistant_id == self.assistant.id and workspace_id == self.assistant.workspace_id else None
        return self.source if source_id == self.source.id and workspace_id == self.source.workspace_id else None

    def attach(self, *, assistant_id, source_id, workspace_id):
        self.links.add(source_id)

    def detach(self, *, assistant_id, source_id, workspace_id):
        self.links.discard(source_id)

    def list_source_ids(self, *, assistant_id, workspace_id):
        return frozenset(self.links)


def test_scope_attach_list_detach_and_cross_workspace_denial() -> None:
    w1, w2 = WorkspaceId(uuid4()), WorkspaceId(uuid4())
    assistant = Assistant.create(workspace_id=w1, name="a", description=None, instructions="i", language="en", model_configuration=ModelConfiguration("p", "m"), retrieval_configuration=RetrievalConfiguration())
    source = KnowledgeSource.create(workspace_id=w1, name="s", kind=KnowledgeSourceKind.DOCUMENT)
    repo = Repo(assistant, source)
    service = AssistantKnowledgeScopeService(assistants=repo, sources=repo, associations=repo)
    service.attach(workspace_id=w1, assistant_id=assistant.id, source_id=source.id)
    assert service.source_ids(workspace_id=w1, assistant_id=assistant.id) == frozenset({source.id})
    service.detach(workspace_id=w1, assistant_id=assistant.id, source_id=source.id)
    assert service.source_ids(workspace_id=w1, assistant_id=assistant.id) == frozenset()
    with pytest.raises(LookupError):
        service.attach(workspace_id=w2, assistant_id=assistant.id, source_id=source.id)
