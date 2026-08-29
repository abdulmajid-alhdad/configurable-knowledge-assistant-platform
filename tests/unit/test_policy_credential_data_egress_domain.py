"""Focused tests for policy, credential, and data-egress contracts."""

from dataclasses import FrozenInstanceError, fields
from typing import cast

import pytest

from knowledge_platform.modules.conversation.domain.conversation import Conversation
from knowledge_platform.modules.conversation.domain.message import Message
from knowledge_platform.modules.evidence_grounding.domain.contracts import Evidence
from knowledge_platform.modules.knowledge_sources.domain.knowledge_source import KnowledgeSource
from knowledge_platform.modules.retrieval_orchestration.domain.contracts import (
    RetrievalPlan,
    RetrievalRequest,
)
from knowledge_platform.modules.workspace_assistant.domain.assistant import Assistant
from knowledge_platform.modules.workspace_assistant.domain.security import (
    CredentialReference,
    DataEgressPolicy,
    PolicyDecision,
    ProcessingLocation,
)
from knowledge_platform.modules.workspace_assistant.ports.credentials import CredentialResolverPort


class DeterministicResolver:
    def resolve(self, reference: CredentialReference) -> str:
        return {"model-api": "test-secret"}[reference.name]


def test_policy_decision_values_are_exact() -> None:
    assert {decision.value for decision in PolicyDecision} == {"allow", "deny"}


def test_processing_location_values_are_exact() -> None:
    assert {location.value for location in ProcessingLocation} == {"local", "external"}


def test_credential_reference_contains_only_a_normalized_logical_name() -> None:
    reference = CredentialReference(name=" model-api ")

    assert reference.name == "model-api"
    assert {field.name for field in fields(reference)} == {"name"}
    assert not hasattr(reference, "value")
    assert not hasattr(reference, "secret")
    with pytest.raises(ValueError, match="name must not be blank"):
        CredentialReference(name=" ")
    with pytest.raises(FrozenInstanceError):
        reference.__setattr__("name", "changed")


def test_resolver_port_accepts_a_framework_free_test_double() -> None:
    resolver: CredentialResolverPort = DeterministicResolver()
    assert resolver.resolve(CredentialReference(name="model-api")) == "test-secret"


@pytest.mark.parametrize("contains_private_data", [False, True])
def test_local_processing_is_always_allowed(contains_private_data: bool) -> None:
    assert DataEgressPolicy().decide(
        processing_location=ProcessingLocation.LOCAL,
        contains_private_data=contains_private_data,
    ) is PolicyDecision.ALLOW


def test_external_non_private_processing_is_allowed() -> None:
    assert DataEgressPolicy().decide(
        processing_location=ProcessingLocation.EXTERNAL,
        contains_private_data=False,
    ) is PolicyDecision.ALLOW


def test_external_private_processing_fails_closed_by_default() -> None:
    policy = DataEgressPolicy()
    assert policy.external_private_data_allowed is False
    assert policy.decide(
        processing_location=ProcessingLocation.EXTERNAL,
        contains_private_data=True,
    ) is PolicyDecision.DENY


def test_external_private_processing_requires_explicit_trusted_allowance() -> None:
    policy = DataEgressPolicy(external_private_data_allowed=True)
    assert policy.decide(
        processing_location=ProcessingLocation.EXTERNAL,
        contains_private_data=True,
    ) is PolicyDecision.ALLOW


def test_untrusted_strings_are_not_inputs_to_policy_decisions() -> None:
    assert {field.name for field in fields(DataEgressPolicy)} == {
        "external_private_data_allowed"
    }
    decision_parameters = DataEgressPolicy.decide.__annotations__
    assert set(decision_parameters) == {
        "processing_location", "contains_private_data", "return"
    }


def test_policy_rejects_invalid_runtime_values_and_is_immutable() -> None:
    policy = DataEgressPolicy()
    with pytest.raises(TypeError, match="processing_location"):
        policy.decide(
            processing_location=cast(ProcessingLocation, "external"),
            contains_private_data=True,
        )
    with pytest.raises(TypeError, match="boolean"):
        DataEgressPolicy(external_private_data_allowed=cast(bool, 1))
    with pytest.raises(FrozenInstanceError):
        policy.__setattr__("external_private_data_allowed", True)


def test_existing_domain_entities_have_no_credential_material_fields() -> None:
    forbidden = {"secret", "password", "token", "api_key", "dsn", "credential_value"}
    for contract in (
        Assistant,
        Conversation,
        Message,
        RetrievalRequest,
        RetrievalPlan,
        Evidence,
        KnowledgeSource,
    ):
        assert {field.name for field in fields(contract)}.isdisjoint(forbidden)
