"""Unit tests for knowledge sources, lifecycle, and explicit access."""

from dataclasses import FrozenInstanceError, fields
from typing import cast

import pytest

from knowledge_platform.modules.knowledge_sources.domain.access import KnowledgeAccessScope
from knowledge_platform.modules.knowledge_sources.domain.identifiers import KnowledgeSourceId
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.knowledge_sources.domain.lifecycle import (
    KnowledgeSourceKind,
    KnowledgeSourceLifecycle,
)
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.configuration import (
    ModelConfiguration,
    RetrievalConfiguration,
)
from knowledge_platform.modules.workspace_assistant.domain.identifiers import (
    AssistantId,
    WorkspaceId,
)


def assistant(*, workspace_id: WorkspaceId | None = None) -> Assistant:
    return Assistant.create(
        workspace_id=workspace_id or WorkspaceId.new(),
        name="Assistant",
        description=None,
        instructions="Answer from selected sources.",
        language="en",
        model_configuration=ModelConfiguration(provider="provider", model_reference="model"),
        retrieval_configuration=RetrievalConfiguration(),
    )


def source(
    *,
    workspace_id: WorkspaceId,
    name: str = "Source",
    kind: KnowledgeSourceKind = KnowledgeSourceKind.DOCUMENT,
) -> KnowledgeSource:
    return KnowledgeSource.create(workspace_id=workspace_id, name=name, kind=kind)


def test_create_generates_registered_source_and_normalizes_name() -> None:
    workspace_id = WorkspaceId.new()
    created = KnowledgeSource.create(
        workspace_id=workspace_id,
        name=" Reference Documents ",
        kind=KnowledgeSourceKind.DOCUMENT,
    )

    assert isinstance(created.id, KnowledgeSourceId)
    assert created.workspace_id == workspace_id
    assert created.name == "Reference Documents"
    assert created.kind is KnowledgeSourceKind.DOCUMENT
    assert created.lifecycle is KnowledgeSourceLifecycle.REGISTERED


def test_source_supports_explicit_identity_rehydration() -> None:
    source_id = KnowledgeSourceId.new()
    workspace_id = WorkspaceId.new()
    restored = KnowledgeSource(
        id=source_id,
        workspace_id=workspace_id,
        name="Database",
        kind=KnowledgeSourceKind.STRUCTURED,
        lifecycle=KnowledgeSourceLifecycle.READY,
    )

    assert restored.id == source_id
    assert restored.workspace_id == workspace_id


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_source_rejects_blank_name(name: str) -> None:
    with pytest.raises(ValueError, match="name must not be blank"):
        source(workspace_id=WorkspaceId.new(), name=name)


def test_source_rejects_invalid_runtime_domain_types() -> None:
    workspace_id = WorkspaceId.new()
    with pytest.raises(TypeError, match="workspace_id must be a WorkspaceId"):
        KnowledgeSource.create(
            workspace_id=cast(WorkspaceId, object()),
            name="Source",
            kind=KnowledgeSourceKind.DOCUMENT,
        )
    with pytest.raises(TypeError, match="kind must be a KnowledgeSourceKind"):
        KnowledgeSource.create(
            workspace_id=workspace_id,
            name="Source",
            kind=cast(KnowledgeSourceKind, "document"),
        )


def test_source_is_immutable_and_identity_distinguishes_entities() -> None:
    workspace_id = WorkspaceId.new()
    first = source(workspace_id=workspace_id)
    second = source(workspace_id=workspace_id)

    assert first != second
    with pytest.raises(FrozenInstanceError):
        first.__setattr__("name", "Changed")


def test_source_kinds_are_exactly_document_and_structured() -> None:
    assert {kind.value for kind in KnowledgeSourceKind} == {"document", "structured"}


_VALID_TRANSITIONS = {
    (KnowledgeSourceLifecycle.REGISTERED, "begin_preparation"): KnowledgeSourceLifecycle.PREPARING,
    (KnowledgeSourceLifecycle.FAILED, "begin_preparation"): KnowledgeSourceLifecycle.PREPARING,
    (KnowledgeSourceLifecycle.PREPARING, "mark_ready"): KnowledgeSourceLifecycle.READY,
    (KnowledgeSourceLifecycle.PREPARING, "mark_failed"): KnowledgeSourceLifecycle.FAILED,
    (KnowledgeSourceLifecycle.READY, "disable"): KnowledgeSourceLifecycle.DISABLED,
    (KnowledgeSourceLifecycle.DISABLED, "enable"): KnowledgeSourceLifecycle.READY,
    (KnowledgeSourceLifecycle.READY, "begin_removal"): KnowledgeSourceLifecycle.REMOVING,
    (KnowledgeSourceLifecycle.DISABLED, "begin_removal"): KnowledgeSourceLifecycle.REMOVING,
    (KnowledgeSourceLifecycle.REMOVING, "mark_removed"): KnowledgeSourceLifecycle.REMOVED,
}


def test_lifecycle_has_exact_values_and_operations() -> None:
    assert {state.value for state in KnowledgeSourceLifecycle} == {
        "registered", "preparing", "ready", "disabled", "failed", "removing", "removed",
    }
    assert set(_VALID_TRANSITIONS) == {
        (state, operation)
        for state in KnowledgeSourceLifecycle
        for operation in (
            "begin_preparation", "mark_ready", "mark_failed", "disable",
            "enable", "begin_removal", "mark_removed",
        )
        if (state, operation) in _VALID_TRANSITIONS
    }


def test_all_lifecycle_operation_combinations_are_operation_specific() -> None:
    operations = (
        "begin_preparation", "mark_ready", "mark_failed", "disable",
        "enable", "begin_removal", "mark_removed",
    )
    valid = invalid = 0
    for state in KnowledgeSourceLifecycle:
        original = KnowledgeSource(
            id=KnowledgeSourceId.new(), workspace_id=WorkspaceId.new(), name="Source",
            kind=KnowledgeSourceKind.STRUCTURED, lifecycle=state,
        )
        for operation in operations:
            try:
                updated = getattr(original, operation)()
            except ValueError:
                invalid += 1
            else:
                valid += 1
                assert updated.lifecycle is _VALID_TRANSITIONS[(state, operation)]
                assert (updated.id, updated.workspace_id, updated.name, updated.kind) == (
                    original.id, original.workspace_id, original.name, original.kind,
                )
    assert valid == 9
    assert invalid == 40


def test_invalid_operation_examples_and_readiness() -> None:
    disabled = KnowledgeSource(
        id=KnowledgeSourceId.new(), workspace_id=WorkspaceId.new(), name="Source",
        kind=KnowledgeSourceKind.STRUCTURED, lifecycle=KnowledgeSourceLifecycle.DISABLED,
    )
    preparing = source(workspace_id=WorkspaceId.new()).begin_preparation()
    with pytest.raises(ValueError):
        disabled.mark_ready()
    with pytest.raises(ValueError):
        preparing.enable()
    for state in KnowledgeSourceLifecycle:
        current = KnowledgeSource(
            id=KnowledgeSourceId.new(), workspace_id=WorkspaceId.new(), name="Source",
            kind=KnowledgeSourceKind.DOCUMENT, lifecycle=state,
        )
        assert current.is_retrieval_eligible is (state is KnowledgeSourceLifecycle.READY)


def test_lifecycle_transitions_preserve_source_invariants() -> None:
    original = source(workspace_id=WorkspaceId.new()).begin_preparation()
    updated = original.mark_ready()
    assert (updated.id, updated.workspace_id, updated.name, updated.kind) == (
        original.id,
        original.workspace_id,
        original.name,
        original.kind,
    )
    assert original.lifecycle is KnowledgeSourceLifecycle.PREPARING


def test_rename_is_validated_and_preserves_all_other_state() -> None:
    original = source(workspace_id=WorkspaceId.new()).begin_preparation().mark_ready()
    renamed = original.rename(name=" Renamed ")

    assert renamed.name == "Renamed"
    assert (renamed.id, renamed.workspace_id, renamed.kind, renamed.lifecycle) == (
        original.id,
        original.workspace_id,
        original.kind,
        original.lifecycle,
    )
    with pytest.raises(ValueError, match="name must not be blank"):
        original.rename(name=" ")


def test_empty_scope_is_explicit_deny_all() -> None:
    owner = assistant()
    scope = KnowledgeAccessScope.for_assistant(assistant=owner, sources=[])
    candidate = source(workspace_id=owner.workspace_id)

    assert scope.source_ids == frozenset()
    assert not scope.allows(candidate)


def test_scope_selects_sources_and_collapses_duplicates() -> None:
    owner = assistant()
    selected = source(workspace_id=owner.workspace_id)
    scope = KnowledgeAccessScope.for_assistant(
        assistant=owner,
        sources=[selected, selected],
    )

    assert scope.source_ids == frozenset({selected.id})
    assert scope.allows(selected)
    assert not scope.allows(source(workspace_id=owner.workspace_id))


def test_scope_rejects_cross_workspace_sources() -> None:
    owner = assistant()
    other_source = source(workspace_id=WorkspaceId.new())

    with pytest.raises(ValueError, match="different workspace"):
        KnowledgeAccessScope.for_assistant(assistant=owner, sources=[other_source])


def test_replace_sources_replaces_complete_set_immutably() -> None:
    owner = assistant()
    first = source(workspace_id=owner.workspace_id)
    second = source(workspace_id=owner.workspace_id)
    original = KnowledgeAccessScope.for_assistant(assistant=owner, sources=[first])

    replacement = original.replace_sources(assistant=owner, sources=[second])

    assert original.source_ids == frozenset({first.id})
    assert replacement.source_ids == frozenset({second.id})
    assert replacement.assistant_id == original.assistant_id
    assert replacement.workspace_id == original.workspace_id


def test_replace_sources_rejects_wrong_assistant_identity_or_workspace() -> None:
    owner = assistant()
    scope = KnowledgeAccessScope.for_assistant(assistant=owner, sources=[])
    wrong_identity = assistant(workspace_id=owner.workspace_id)
    wrong_workspace = Assistant(
        id=owner.id,
        workspace_id=WorkspaceId.new(),
        name=owner.name,
        description=owner.description,
        instructions=owner.instructions,
        language=owner.language,
        model_configuration=owner.model_configuration,
        retrieval_configuration=owner.retrieval_configuration,
    )

    with pytest.raises(ValueError, match="identity"):
        scope.replace_sources(assistant=wrong_identity, sources=[])
    with pytest.raises(ValueError, match="workspace"):
        scope.replace_sources(assistant=wrong_workspace, sources=[])


def test_allows_rejects_cross_workspace_even_if_identity_is_selected() -> None:
    owner = assistant()
    selected = source(workspace_id=owner.workspace_id)
    scope = KnowledgeAccessScope.for_assistant(assistant=owner, sources=[selected])
    cross_workspace_copy = KnowledgeSource(
        id=selected.id,
        workspace_id=WorkspaceId.new(),
        name=selected.name,
        kind=selected.kind,
        lifecycle=selected.lifecycle,
    )

    assert not scope.allows(cross_workspace_copy)


def test_access_scope_is_immutable_and_schema_bounded() -> None:
    scope = KnowledgeAccessScope.for_assistant(assistant=assistant(), sources=[])

    with pytest.raises(FrozenInstanceError):
        scope.__setattr__("source_ids", frozenset())
    assert {field.name for field in fields(scope)} == {
        "assistant_id",
        "workspace_id",
        "source_ids",
    }


def test_contract_has_no_configuration_credentials_or_readiness_state() -> None:
    source_fields = {field.name for field in fields(KnowledgeSource)}
    scope_fields = {field.name for field in fields(KnowledgeAccessScope)}

    assert source_fields == {"id", "workspace_id", "name", "kind", "lifecycle"}
    assert scope_fields == {"assistant_id", "workspace_id", "source_ids"}
    assert {state.value for state in KnowledgeSourceLifecycle} == {
        "registered", "preparing", "ready", "disabled", "failed", "removing", "removed",
    }
    assert "knowledge_access_scopes" not in {field.name for field in fields(Assistant)}
    assert not hasattr(KnowledgeSource, "configuration")
    assert not hasattr(KnowledgeSource, "credential_reference")
    assert not hasattr(KnowledgeSource, "ready")


def test_access_scope_rejects_invalid_runtime_values() -> None:
    with pytest.raises(TypeError, match="assistant_id"):
        KnowledgeAccessScope(
            assistant_id=cast(AssistantId, object()),
            workspace_id=WorkspaceId.new(),
            source_ids=frozenset(),
        )
