"""Minimal validation shared within the knowledge sources domain."""


def required_text(value: str, *, field: str) -> str:
    """Return normalized required text or reject an invalid value."""
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be blank")
    return normalized
