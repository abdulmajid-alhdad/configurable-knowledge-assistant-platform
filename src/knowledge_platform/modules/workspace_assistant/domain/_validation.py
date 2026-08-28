"""Minimal text validation shared within the workspace assistant domain."""


def required_text(value: str, *, field: str) -> str:
    """Return normalized required text or reject an invalid value."""
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be blank")
    return normalized


def optional_text(value: str | None, *, field: str) -> str | None:
    """Return normalized optional text, preserving absence as None."""
    if value is None:
        return None
    return required_text(value, field=field)
