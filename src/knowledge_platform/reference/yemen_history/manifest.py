"""Declarative Yemen reference configuration."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReferenceDefinition:
    key: str
    workspace_name: str
    assistant_name: str
    assistant_instructions: str
    source_name: str
    artifact_name: str


DEFINITION = ReferenceDefinition(
    key="yemen_history",
    workspace_name="Yemen History Reference",
    assistant_name="Yemen History Assistant",
    assistant_instructions="Answer Arabic historical questions only from supplied evidence.",
    source_name="Yemen History Reference Source",
    artifact_name="yemen_history.md",
)


def artifact_path() -> Path:
    return Path(__file__).with_name("knowledge") / DEFINITION.artifact_name
