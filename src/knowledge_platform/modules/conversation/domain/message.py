"""Immutable conversation messages."""

from dataclasses import dataclass

from .roles import MessageRole


@dataclass(frozen=True, slots=True)
class Message:
    sequence: int
    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise TypeError("sequence must be an integer")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if not isinstance(self.role, MessageRole):
            raise TypeError("role must be a MessageRole")
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")
        normalized = self.content.strip()
        if not normalized:
            raise ValueError("content must not be blank")
        object.__setattr__(self, "content", normalized)
