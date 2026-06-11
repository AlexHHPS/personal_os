"""TECH STACK extraction + system-prompt constraints block builder.

Verbatim port of the ``_extract_tech_stack_section`` /
``_build_constraints_block`` helpers from
``pm_engine.crew.crew`` (lines 38-95 in the dissolved repo).

These two constraints are pinned into every brain call's system prompt:

1. **TECH STACK** — extracted from the PRD's "Tech Stack" /
   "Recommended Tech Stack" / "Technology Stack" section. Forces the
   model to draw ``affected_modules`` from a known allow-list rather
   than inventing libraries / runtimes.
2. **NUMERIC THRESHOLDS** — any percentage / ratio / count / latency
   bound not literally in the PRD must carry an inline
   ``[ASSUMPTION: rationale]`` tag, so invented thresholds become
   detectable in downstream review.
"""

from __future__ import annotations

import re

_TECH_STACK_HEADING_RE = re.compile(
    r"^#{1,6}\s+(?:recommended\s+)?tech(?:nology)?\s+stack\b[^\n]*$"
    r"\n(?P<body>.*?)"  # consume only the heading's trailing newline; body is non-greedy
    r"(?=\n#{1,6}\s|\Z)",  # boundary: blank-line-then-heading, or EOF
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def extract_tech_stack(prd_text: str) -> str:
    """Extract the body of a 'Tech Stack' heading from a PRD.

    Matches ``# Tech Stack`` / ``## Technology Stack`` /
    ``## Recommended Tech Stack`` (case-insensitive). Returns the raw
    markdown body of the matched section, trimmed.

    Falls back to a "no constraints declared" sentinel when the PRD has
    no such section — downstream agents must treat that as "no stack
    restrictions".
    """
    match = _TECH_STACK_HEADING_RE.search(prd_text)
    if match is None:
        return "(No tech stack constraints declared in PRD — no module restrictions.)"
    return match.group("body").strip() or (
        "(Tech stack section present but empty — no module restrictions.)"
    )


def build_constraints_block(em_context: str, tech_stack_section: str) -> str:
    """Compose the immutable constraints block prepended to every call's system prompt.

    Args:
        em_context: Optional engineering-manager context. May be empty.
        tech_stack_section: Output of :func:`extract_tech_stack`.

    Returns:
        Markdown string with two pinned constraints (TECH STACK +
        NUMERIC THRESHOLDS). Per-task ``ROLE`` text is appended by the
        orchestrator after this block.
    """
    base = em_context.rstrip()
    separator = "\n\n" if base else ""
    return (
        f"{base}{separator}"
        "# IMMUTABLE CONSTRAINTS\n"
        "(Apply to every output you produce. Violating these is a hard error.)\n\n"
        "## TECH STACK (declared in PRD)\n"
        f"{tech_stack_section}\n\n"
        "Use ONLY the technologies above when discussing implementation.\n"
        "Inventing modules / libraries / runtimes outside this list is\n"
        "forbidden. If a needed capability is missing, raise it as an open\n"
        "question — do not silently substitute.\n\n"
        "## NUMERIC THRESHOLDS\n"
        "Any numeric threshold (percentage, ratio, count, latency bound,\n"
        "budget margin) that is NOT literally present in the PRD MUST be\n"
        "tagged inline with `[ASSUMPTION: <rationale>]`. Do not invent\n"
        "thresholds without a tag.\n"
    )


def role_system(em_context: str, tech_stack_section: str, role: str) -> str:
    """Compose a full system prompt: immutable constraints + the call's role."""
    block = build_constraints_block(em_context, tech_stack_section)
    return f"{block}\n## YOUR ROLE\n{role}\n"
