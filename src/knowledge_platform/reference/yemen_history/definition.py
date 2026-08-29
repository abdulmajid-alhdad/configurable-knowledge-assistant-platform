"""Ordinary Yemen History reference configuration using Core contracts."""

from knowledge_platform.modules.knowledge_sources.domain.access import KnowledgeAccessScope
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import KnowledgeSourceKind
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace


def build_reference() -> tuple[Workspace, Assistant, KnowledgeSource, KnowledgeAccessScope]:
    workspace = Workspace.create(name="Yemen History Demo")
    assistant = Assistant.create(
        workspace_id=workspace.id,
        name="Yemen History Assistant",
        description="Arabic grounded history demo",
        instructions="Answer Arabic historical questions only from supplied evidence.",
        language="ar",
        model_configuration=ModelConfiguration(
            provider="remote", model_reference="reference-model"
        ),
        retrieval_configuration=RetrievalConfiguration(),
    )
    source = KnowledgeSource.create(
        workspace_id=workspace.id,
        name="Yemen History Demo Fixture",
        kind=KnowledgeSourceKind.DOCUMENT,
    )
    return workspace, assistant, source, KnowledgeAccessScope.for_assistant(
        assistant=assistant, sources=[source]
    )
