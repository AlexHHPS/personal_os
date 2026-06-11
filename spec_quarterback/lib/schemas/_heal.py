"""Shared self-healing helpers for the lenient generator schemas.

The generator binds model responses to these schemas. A single non-conforming
field used to fail a whole document, so nothing got written. As in the legacy
flat ``Spec`` schema, we prefer *always writing* a document over strict
rejection: ``mode="before"`` validators coerce the common model mistakes
(blank fields, non-list values, missing keys) into a valid shape, and the
critic's quality bar — not Pydantic — is what drives the content to improve.
"""

from __future__ import annotations

PLACEHOLDER = "(unspecified)"


def nonempty_str(value: object, *, default: str = PLACEHOLDER) -> str:
    """Return a trimmed string, or ``default`` when value is empty/None."""
    text = str(value).strip() if value is not None else ""
    return text or default


def str_list(value: object) -> list[str]:
    """Coerce ``value`` into a list of non-empty trimmed strings."""
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = []
    return [s for s in (str(x).strip() for x in items) if s]


def nonempty_str_list(value: object, *, default: str = PLACEHOLDER) -> list[str]:
    """Like :func:`str_list` but guarantees at least one (placeholder) item."""
    items = str_list(value)
    return items or [default]


def derive_title(text: str, *, max_words: int = 8) -> str:
    """Synthesize a short title from a longer text (model often omits title)."""
    words = text.split()
    if not words or text == PLACEHOLDER:
        return PLACEHOLDER
    return " ".join(words[:max_words]).rstrip(".,;:")
