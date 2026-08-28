"""Unit tests for the Workspace and Assistant domain model."""

from dataclasses import FrozenInstanceError, fields
from inspect import signature
from typing import cast

import pytest

from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)
from knowledge_platform.modules.workspace_assistant.domain.workspace import Workspace


def model_configuration() -> ModelConfiguration:
    return ModelConfiguration(provider=" openrouter ", model_reference=" openai/gpt-4.1 ")


def retrieval_configuration() -> RetrievalConfiguration:
    return RetrievalConfiguration()


def assistant(*, workspace_id: WorkspaceId | None = None) -> Assistant:
    return Assistant.create(
        workspace_id=workspace_id or WorkspaceId.new(),
        name=" Research Assistant ",
        description=" Evidence-focused assistant ",
        instructions=" Answer with cited evidence. ",
        language=" en ",
        model_configuration=model_configuration(),
        retrieval_configuration=retrieval_configuration(),
    )


def test_workspace_creation_generates_identity_and_normalizes_name() -> None:
    workspace = Workspace.create(name=" Research Workspace ")

    assert isinstance(workspace.id, WorkspaceId)
    assert workspace.name == "Research Workspace"


def test_workspace_can_be_constructed_with_an_existing_identity() -> None:
    workspace_id = WorkspaceId.new()

    workspace = Workspace(id=workspace_id, name="Existing Workspace")

    assert workspace.id == workspace_id


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_workspace_rejects_blank_name(name: str) -> None:
    with pytest.raises(ValueError, match="name must not be blank"):
        Workspace.create(name=name)


def test_workspaces_with_the_same_name_and_different_ids_remain_distinct() -> None:
    first = Workspace(id=WorkspaceId.new(), name="Same Name")
    second = Workspace(id=WorkspaceId.new(), name="Same Name")

    assert first != second


def test_model_configuration_is_validated_normalized_and_secret_free() -> None:
    configuration = model_configuration()

    assert configuration.provider == "openrouter"
    assert configuration.model_reference == "openai/gpt-4.1"
    assert {field.name for field in fields(configuration)} == {"provider", "model_reference"}


@pytest.mark.parametrize(
    ("provider", "model_reference", "field"),
    [
        ("", "model", "provider"),
        (" ", "model", "provider"),
        ("provider", "", "model_reference"),
        ("provider", "\t", "model_reference"),
    ],
)
def test_model_configuration_rejects_blank_values(
    provider: str,
    model_reference: str,
    field: str,
) -> None:
    with pytest.raises(ValueError, match=f"{field} must not be blank"):
        ModelConfiguration(provider=provider, model_reference=model_reference)


def test_model_configuration_is_immutable() -> None:
    configuration = model_configuration()

    with pytest.raises(FrozenInstanceError):
        configuration.__setattr__("provider", "ollama")


def test_default_retrieval_configuration_is_explicit_immutable_and_schema_bounded() -> None:
    configuration = RetrievalConfiguration()

    assert fields(configuration) == ()
    assert tuple(signature(RetrievalConfiguration).parameters) == ()
    with pytest.raises((FrozenInstanceError, TypeError)):
        configuration.__setattr__("top_k", 5)


def test_assistant_creation_validates_and_retains_workspace_ownership() -> None:
    workspace_id = WorkspaceId.new()

    created = assistant(workspace_id=workspace_id)

    assert isinstance(created.id, AssistantId)
    assert created.workspace_id == workspace_id
    assert created.name == "Research Assistant"
    assert created.description == "Evidence-focused assistant"
    assert created.instructions == "Answer with cited evidence."
    assert created.language == "en"
    assert isinstance(created.model_configuration, ModelConfiguration)
    assert isinstance(created.retrieval_configuration, RetrievalConfiguration)


def test_assistant_can_be_constructed_with_an_existing_identity() -> None:
    assistant_id = AssistantId.new()
    workspace_id = WorkspaceId.new()

    rehydrated = Assistant(
        id=assistant_id,
        workspace_id=workspace_id,
        name="Assistant",
        description=None,
        instructions="Follow instructions",
        language="en",
        model_configuration=model_configuration(),
        retrieval_configuration=retrieval_configuration(),
    )

    assert rehydrated.id == assistant_id
    assert rehydrated.workspace_id == workspace_id


@pytest.mark.parametrize("field", ["name", "instructions", "language"])
def test_assistant_rejects_blank_required_text(field: str) -> None:
    values = {
        "name": "Assistant",
        "instructions": "Follow instructions",
        "language": "en",
    }
    values[field] = "  "

    with pytest.raises(ValueError, match=f"{field} must not be blank"):
        Assistant.create(
            workspace_id=WorkspaceId.new(),
            name=values["name"],
            description=None,
            instructions=values["instructions"],
            language=values["language"],
            model_configuration=model_configuration(),
            retrieval_configuration=retrieval_configuration(),
        )


def test_assistant_rejects_invalid_model_configuration_reference() -> None:
    invalid_configuration = cast(ModelConfiguration, object())

    with pytest.raises(TypeError, match="model_configuration must be a ModelConfiguration"):
        Assistant.create(
            workspace_id=WorkspaceId.new(),
            name="Assistant",
            description=None,
            instructions="Follow instructions",
            language="en",
            model_configuration=invalid_configuration,
            retrieval_configuration=retrieval_configuration(),
        )


def test_assistant_has_no_lifecycle_or_knowledge_scope_fields() -> None:
    field_names = {field.name for field in fields(Assistant)}

    assert "status" not in field_names
    assert "lifecycle" not in field_names
    assert "knowledge_access_scopes" not in field_names


def test_valid_reconfiguration_preserves_identity_and_workspace() -> None:
    original = assistant()
    replacement_model = ModelConfiguration(provider="ollama", model_reference="qwen3")
    replacement_retrieval = RetrievalConfiguration()

    updated = original.reconfigure(
        name="Updated Assistant",
        description=None,
        instructions="Use the updated instructions.",
        language="ar",
        model_configuration=replacement_model,
        retrieval_configuration=replacement_retrieval,
    )

    assert updated.id == original.id
    assert updated.workspace_id == original.workspace_id
    assert updated.name == "Updated Assistant"
    assert updated.description is None
    assert updated.model_configuration == replacement_model
    assert updated.retrieval_configuration == replacement_retrieval
    assert original.name == "Research Assistant"
    assert "workspace_id" not in signature(Assistant.reconfigure).parameters


def test_invalid_reconfiguration_is_rejected_without_changing_original() -> None:
    original = assistant()

    with pytest.raises(ValueError, match="instructions must not be blank"):
        original.reconfigure(
            name="Updated Assistant",
            description="Updated description",
            instructions=" ",
            language="en",
            model_configuration=model_configuration(),
            retrieval_configuration=retrieval_configuration(),
        )

    assert original.instructions == "Answer with cited evidence."
