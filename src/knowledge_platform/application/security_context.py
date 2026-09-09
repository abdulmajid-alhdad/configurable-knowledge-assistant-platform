"""Request-local authenticated identity used to establish database GUCs."""

from contextvars import ContextVar, Token
from uuid import UUID

_current_user: ContextVar[UUID | None] = ContextVar("current_user", default=None)


def current_user_id() -> UUID | None:
    return _current_user.get()


def bind_user(user_id: UUID) -> Token[UUID | None]:
    return _current_user.set(user_id)


def reset_user(token: Token[UUID | None]) -> None:
    _current_user.reset(token)
