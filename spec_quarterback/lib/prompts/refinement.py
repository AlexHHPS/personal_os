"""Refinement prompts — the critic-driven improve step.

The *critic review* system prompt is NOT here: it is loaded live from
``specs/template/critic/spec_quality_reviewer_prompt.md`` via the templates
loader, so editing that file retunes the rubric with no code change. This module
holds only the **improve** prompt — the editor that rewrites a single document
to resolve the critic's issues for it.

Placeholders filled by the improve step: ``{{doc_kind}}``, ``{{skeleton}}``,
``{{doc_json}}``, ``{{issues}}``, ``{{consistency}}``.
"""

from __future__ import annotations

from typing import Final

IMPROVE_ROLE: Final[str] = (
    "Spec Editor. Goal: rewrite ONE document of an SDD set to resolve the "
    "critic's issues for that document, keeping it consistent with the rest of "
    "the set. Improve substance, not length."
)
IMPROVE_TEMPERATURE: Final[float] = 0.1

IMPROVE_PROMPT: Final[str] = """\
Rewrite the {{doc_kind}} document to resolve every issue listed below. Output the
SAME JSON structure as the input (the same top-level keys), improved.

Hard rules:
- preserve `feature_id` exactly; do not rename it.
- preserve existing ids (US-/EC-/T- ids, entity/component names) unless an issue
  explicitly calls for a rename.
- match the spec's scope to the PRD: add or correct exactly the requirement the critic flagged
  with "[PRD MISSING]", "[PRD CONTRADICTED]", or "[PRD PARTIAL]" (quoted in the issue), and
  REMOVE the scope flagged "[PRD INVENTED]" (the PRD does not ask for it). Make no other scope
  changes — otherwise only tighten, clarify, complete, and make criteria testable.
- honor the IMMUTABLE CONSTRAINTS in your system prompt (TECH STACK, threshold
  tagging with `[ASSUMPTION: <rationale>]`).
- STAY CONSISTENT with the anchors below: reuse the EXACT entity names, field names,
  field types, enum values, endpoint paths, and file paths they define. Do NOT invent
  a different shape (e.g. a different column set, type, or route) for something already
  defined there — that is the cross-document drift the critic penalizes.

# Consistency anchors (authoritative — do not diverge)
{{consistency}}

# Target structure (skeleton)
{{skeleton}}

# Current {{doc_kind}} document
{{doc_json}}

# Issues to resolve (from the critic)
{{issues}}

Output a SINGLE JSON object only — no markdown fences, no commentary.
"""
