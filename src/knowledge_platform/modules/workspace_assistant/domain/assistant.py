"""Assistant aggregate root."""

from dataclasses import dataclass
from typing import Self

from ._validation import optional_text, required_text
from .configuration import ModelConfiguration, RetrievalConfiguration
from .identifiers import AssistantId, WorkspaceId


@dataclass(frozen=True, slots=True)
class Assistant:
    """An independently configured assistant owned by one workspace."""

    id: AssistantId
    workspace_id: WorkspaceId
    name: str
    description: str | None
    instructions: str
    language: str
    model_configuration: ModelConfiguration
    retrieval_configuration: RetrievalConfiguration

    def __post_init__(self) -> None:
        if not isinstance(self.id, AssistantId):
            raise TypeError("id must be an AssistantId")
        if not isinstance(self.workspace_id, WorkspaceId):
            raise TypeError("workspace_id must be a WorkspaceId")
        if not isinstance(self.model_configuration, ModelConfiguration):
            raise TypeError("model_configuration must be a ModelConfiguration")
        if not isinstance(self.retrieval_configuration, RetrievalConfiguration):
            raise TypeError("retrieval_configuration must be a RetrievalConfiguration")

        object.__setattr__(self, "name", required_text(self.name, field="name"))
        object.__setattr__(
            self,
            "description",
            optional_text(self.description, field="description"),
        )
        object.__setattr__(
            self,
            "instructions",
            required_text(self.instructions, field="instructions"),
        )
        object.__setattr__(self, "language", required_text(self.language, field="language"))

    @classmethod
    def create(
        cls,
        *,
        workspace_id: WorkspaceId,
        name: str,
        description: str | None,
        instructions: str,
        language: str,
        model_configuration: ModelConfiguration,
        retrieval_configuration: RetrievalConfiguration,
    ) -> Self:
        """Create a validated assistant with a generated identity."""
        return cls(
            id=AssistantId.new(),
            workspace_id=workspace_id,
            name=name,
            description=description,
            instructions=instructions,
            language=language,
            model_configuration=model_configuration,
            retrieval_configuration=retrieval_configuration,
        )

    def reconfigure(
        self,
        *,
        name: str,
        description: str | None,
        instructions: str,
        language: str,
        model_configuration: ModelConfiguration,
        retrieval_configuration: RetrievalConfiguration,
    ) -> Self:
        """Return a validated replacement without changing identity or ownership."""
        return type(self)(
            id=self.id,
            workspace_id=self.workspace_id,
            name=name,
            description=description,
            instructions=instructions,
            language=language,
            model_configuration=model_configuration,
            retrieval_configuration=retrieval_configuration,
        )
