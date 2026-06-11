"""Flat ``Spec`` schema — the mid-size unit of work emitted by the generator.

This replaces the old Tactic → Epic → Ticket ``DecompositionTree`` plus the
per-leaf ``SpecContract``. A *Spec* is a single self-contained mid-size unit
of work: bigger than a one-line ticket, smaller than a whole PRD. The
generator (``lib.generator``) emits a :class:`SpecList`; the store
(``lib.spec_store``) renders each :class:`Spec` to its own markdown file.

Design notes:

* **Content only.** A ``Spec`` carries *what the work is*. Run/refinement
  metadata (``affected_project``, ``prd_slug``, ``generated_at``,
  ``quality_score``, ``iteration``, ``locked``, ``content_hash``) is NOT
  modelled here — it lives in the markdown front-matter managed by
  ``lib.spec_store``. Keeping it out of the Pydantic schema keeps the
  LLM ``response_format`` payload small and stops the generator from being
  asked to invent metadata it cannot know.
* **GBNF-safe.** Both classes mix in :class:`FlatSchemaMixin` so their
  JSON Schema inlines ``$refs`` and drops ``pattern`` constraints before
  hitting OmniRoute. Pattern enforcement still runs client-side at
  ``model_validate`` time.
* **Flat referential integrity.** Inter-spec ``dependencies`` resolve and
  are acyclic — the flat analogue of the old tree's cross-ticket dependency
  validators.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from spec_quarterback.lib.schemas.schema_flatten import (
    FlatSchemaMixin,
)

logger = logging.getLogger(__name__)

# Use [0-9] rather than \d: these patterns are emitted into JSON Schema, and
# llama.cpp's GBNF translator chokes on PCRE shorthand classes. FlatSchemaMixin
# strips the pattern from the wire schema anyway; this regex is the client-side
# validator.
_SPEC_ID_RE = re.compile(r"^spec-[0-9]+$")
_STORY_POINTS = frozenset({1, 2, 3, 5, 8})

# LENIENT MODE (temporary). The generator binds the model response to this
# schema; a single non-conforming spec used to fail the *whole* SpecList, so
# nothing got written. For now we prefer *always writing* specs over strict
# rejection: the validators below SELF-HEAL the common model mistakes (blank
# fields, duplicate / dangling / self / cyclic dependencies, non-Fibonacci
# points, ready-vs-open-questions conflicts) instead of raising. Tighten this
# once generation output is reliably well-formed.
_PLACEHOLDER = "(unspecified)"


def _nonempty_str(value: object, *, default: str = _PLACEHOLDER) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _derive_title(problem_statement: str, *, max_words: int = 8) -> str:
    """Synthesize a short title from the problem statement.

    The routed model sometimes omits the per-spec ``title`` (it reliably fills
    every other field). Rather than a flat placeholder — which makes filenames
    and the index unreadable — derive a human title from the first words of the
    problem statement so the output stays usable.
    """
    words = problem_statement.split()
    if not words or problem_statement == _PLACEHOLDER:
        return _PLACEHOLDER
    return " ".join(words[:max_words]).rstrip(".,;:")


def _strip_back_edges(deps_by_id: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return a DAG: drop edges that close a cycle (DFS back-edges).

    Cross/forward edges are kept; only edges pointing at a node currently on the
    recursion stack are removed. Mutates a copy, returns the sanitized mapping.
    """
    cleaned: dict[str, list[str]] = {k: list(v) for k, v in deps_by_id.items()}
    visited: set[str] = set()
    on_stack: set[str] = set()

    def dfs(node: str) -> None:
        visited.add(node)
        on_stack.add(node)
        kept: list[str] = []
        for nxt in cleaned.get(node, []):
            if nxt in on_stack:
                logger.warning("[spec] dropping cyclic dependency %s -> %s", node, nxt)
                continue
            if nxt not in visited:
                dfs(nxt)
            kept.append(nxt)
        cleaned[node] = kept
        on_stack.discard(node)

    for node in list(cleaned):
        if node not in visited:
            dfs(node)
    return cleaned


class Spec(FlatSchemaMixin, BaseModel):
    """A mid-size, self-contained unit of work derived from a PRD.

    Every field except ``id``/``title`` mirrors the old ``SpecContract`` —
    the 11-field execution contract is preserved, just hoisted from the
    leaf-ticket level to the flat-spec level and given a stable id/title.
    """

    model_config = ConfigDict(strict=False)

    id: str = Field(
        ...,
        description="Structural identifier: literal 'spec-' + digits, e.g. 'spec-01'.",
    )
    title: str = Field(..., min_length=1, description="Short human title for the spec.")
    problem_statement: str = Field(
        ...,
        min_length=1,
        description="What problem this spec resolves. Substance over length.",
    )
    desired_outcome: str = Field(
        ...,
        min_length=1,
        description="What is true once this spec is done.",
    )
    scope: list[str] = Field(
        ...,
        min_length=1,
        description="What is included in this spec (>=1 item).",
    )
    out_of_scope: list[str] = Field(
        default_factory=list,
        description="What is explicitly excluded.",
    )
    acceptance_criteria: list[str] = Field(
        ...,
        min_length=1,
        description="Verifiable success conditions (>=1 item).",
    )
    affected_modules: list[str] = Field(
        default_factory=list,
        description="Modules/areas touched, drawn from the PRD tech stack.",
    )
    external_dependencies: list[str] = Field(
        default_factory=list,
        description="Libraries, APIs, or external systems required.",
    )
    technical_notes: str = Field(
        default="",
        description="Design decisions, constraints, or implementation guidance.",
    )
    risks: list[str] = Field(
        default_factory=list,
        description="Known or potential risks and mitigations.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Ids of OTHER specs this spec depends on (must resolve, acyclic).",
    )
    open_questions: list[str] | Literal["all_resolved"] = Field(
        default="all_resolved",
        description='Unresolved questions (list) or "all_resolved" if none remain.',
    )
    story_points_estimate: int | None = Field(
        default=None,
        description="Optional Fibonacci estimate (one of 1,2,3,5,8) or null.",
    )
    implementation_ready: bool = Field(
        default=False,
        description="True iff every field is complete and questions resolved.",
    )

    @field_validator("open_questions", mode="before")
    @classmethod
    def _normalise_open_questions(cls, v: object) -> object:
        """Coerce the common "no open questions" model mistakes to the literal.

        Models routinely emit the sentinel wrapped in a list
        (``["all_resolved"]``) or an empty list to mean "nothing unresolved".
        Both normalise to the literal ``"all_resolved"`` so the union type and
        the readiness invariant validate cleanly. A genuine question list is
        preserved (a stray sentinel mixed in is stripped).
        """
        if isinstance(v, list):
            cleaned = [str(x) for x in v if str(x) != "all_resolved"]
            return cleaned or "all_resolved"
        return v

    @model_validator(mode="before")
    @classmethod
    def _self_heal(cls, data: object) -> object:
        """LENIENT MODE: coerce a near-miss spec dict into a valid one.

        Fills blank text fields, guarantees non-empty scope / acceptance
        criteria, dedupes criteria, coerces a non-Fibonacci estimate to ``None``
        and sanitizes ``dependencies`` (well-formed, unique, no self-reference).
        Cross-spec dependency resolution + cycle-breaking happen at the
        ``SpecList`` level (a single Spec cannot see its siblings).
        """
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)

        d["id"] = _nonempty_str(d.get("id"), default="spec-00")
        d["problem_statement"] = _nonempty_str(d.get("problem_statement"))
        d["desired_outcome"] = _nonempty_str(d.get("desired_outcome"))
        # title: keep the model's if present, else derive from the problem
        # statement (the model frequently omits this one field).
        title = str(d.get("title") or "").strip()
        d["title"] = title or _derive_title(str(d["problem_statement"]))

        for key in ("scope", "acceptance_criteria"):
            value = d.get(key)
            items = [str(x) for x in value if str(x).strip()] if isinstance(value, list) else []
            if key == "acceptance_criteria":
                items = list(dict.fromkeys(items))  # must be unique (order-preserving)
            d[key] = items or [_PLACEHOLDER]

        points = d.get("story_points_estimate")
        if points is not None and points not in _STORY_POINTS:
            d["story_points_estimate"] = None

        deps = d.get("dependencies")
        if isinstance(deps, list):
            own_id = d.get("id")
            seen: list[str] = []
            for dep in deps:
                dep_s = str(dep)
                if _SPEC_ID_RE.match(dep_s) and dep_s != own_id and dep_s not in seen:
                    seen.append(dep_s)
            d["dependencies"] = seen
        return d

    @model_validator(mode="after")
    def _reconcile_readiness(self) -> Spec:
        """A spec with unresolved questions cannot be implementation-ready.

        Lenient mode: rather than reject, demote ``implementation_ready`` to
        ``False`` when ``open_questions`` still lists anything.
        """
        if self.implementation_ready and self.open_questions != "all_resolved":
            self.implementation_ready = False
        return self


class SpecList(FlatSchemaMixin, BaseModel):
    """Full set of Specs the generator derived from one PRD.

    This is the generator's structured output. Project context
    (``affected_project``) and timestamps are applied by the store at write
    time, not modelled here.
    """

    model_config = ConfigDict(strict=False)

    prd_title: str = Field(..., min_length=1)
    prd_goal: str = Field(..., min_length=1)
    # LENIENT MODE: was min_length=1; relaxed so an empty list writes nothing
    # rather than failing the whole run.
    specs: list[Spec] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _self_heal(cls, data: object) -> object:
        """LENIENT MODE: fill blank PRD title/goal; coerce specs to a list."""
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)
        d["prd_title"] = _nonempty_str(d.get("prd_title"))
        d["prd_goal"] = _nonempty_str(d.get("prd_goal"))
        if not isinstance(d.get("specs"), list):
            d["specs"] = []
        return d

    @model_validator(mode="after")
    def _dedupe_ids(self) -> SpecList:
        """LENIENT MODE: keep the first spec per id, drop later duplicates."""
        seen: set[str] = set()
        kept: list[Spec] = []
        for spec in self.specs:
            if spec.id in seen:
                logger.warning("[spec] dropping duplicate spec id %s", spec.id)
                continue
            seen.add(spec.id)
            kept.append(spec)
        self.specs = kept
        return self

    @model_validator(mode="after")
    def _sanitize_dependencies(self) -> SpecList:
        """LENIENT MODE: drop dangling dependency ids and break any cycles.

        Runs after :meth:`_dedupe_ids`, so the id set is final. Yields an
        acyclic graph that ``topological_order`` can sort.
        """
        ids = {s.id for s in self.specs}
        deps_by_id = {s.id: [d for d in s.dependencies if d in ids] for s in self.specs}
        deps_by_id = _strip_back_edges(deps_by_id)
        for spec in self.specs:
            spec.dependencies = deps_by_id.get(spec.id, [])
        return self

    def topological_order(self) -> list[Spec]:
        """Return specs in dependency order (a spec follows its dependencies).

        Stable: ties break on the spec's position in ``self.specs``. The
        graph is guaranteed acyclic by ``_validate_dependencies_resolve``.
        """
        by_id = {s.id: s for s in self.specs}
        order_index = {s.id: i for i, s in enumerate(self.specs)}
        ordered: list[Spec] = []
        done: set[str] = set()

        def visit(spec_id: str, path: frozenset[str]) -> None:
            if spec_id in done:
                return
            for dep in sorted(by_id[spec_id].dependencies, key=lambda d: order_index[d]):
                visit(dep, path | {spec_id})
            done.add(spec_id)
            ordered.append(by_id[spec_id])

        for spec in self.specs:
            visit(spec.id, frozenset())
        return ordered
