"""Small text helpers shared across the spec_quarterback flows.

Kept in its own module so both the schemas (``schemas.feature_plan``) and the
store (``spec_store``) can use ``slugify`` without a circular import (the store
imports the schemas, so the schemas cannot import the store).
"""

from __future__ import annotations

import re


def slugify(text: str, *, max_len: int = 60) -> str:
    """Lowercase, hyphenate, strip to a filesystem/URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].strip("-") or "untitled"
