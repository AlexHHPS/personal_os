"""``FeaturePlan`` / ``FeaturePlanList`` — the PRD decomposition schema.

Phase 1 of the generator turns a PRD into a flat list of mid-size *feature*
stubs (the lightweight plan). Phase 2 then expands each feature into its own
SDD document set (``requirements.md`` / ``design.md`` / ``tasks.md``).

Resilience by design: the whole flow runs through LLMs, so format drift is
expected and must never stop the pipeline. There are NO hard validations here —
every field is optional with a default, and ``mode="before"`` healers *coerce*
the common model mistakes (blank fields, a string where a list was expected,
missing keys, self/cyclic/duplicate dependencies) rather than rejecting them.
A near-miss is healed into something usable; the critic, not Pydantic, is the
quality gate.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spec_quarterback.lib.schemas._heal import (
    derive_title,
    nonempty_str,
    nonempty_str_list,
)
from spec_quarterback.lib.text import slugify

logger = logging.getLogger(__name__)

_FEATURE_ID_RE = re.compile(r"^feature-[0-9]+$")


def _strip_back_edges(deps_by_id: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return a DAG: drop edges that close a cycle (DFS back-edges)."""
    cleaned: dict[str, list[str]] = {k: list(v) for k, v in deps_by_id.items()}
    visited: set[str] = set()
    on_stack: set[str] = set()

    def dfs(node: str) -> None:
        visited.add(node)
        on_stack.add(node)
        kept: list[str] = []
        for nxt in cleaned.get(node, []):
            if nxt in on_stack:
                logger.warning("[feature_plan] dropping cyclic dependency %s -> %s", node, nxt)
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


class FeaturePlan(BaseModel):
    """One mid-size feature derived from a PRD — a stub to be expanded."""

    model_config = ConfigDict(strict=False, extra="ignore")

    id: str = Field(default="", description="Structural id: 'feature-' + digits, e.g. feature-01.")
    title: str = Field(default="", description="Short human title (1-8 words).")
    slug: str = Field(default="", description="Filesystem slug; derived from title if blank.")
    problem: str = Field(default="", description="The user/system problem this feature resolves.")
    outcome: str = Field(default="", description="What is true once this feature ships.")
    scope: list[str] = Field(default_factory=list, description="What this feature includes.")
    dependencies: list[str] = Field(
        default_factory=list, description="Ids of OTHER features this one depends on."
    )

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)
        d["id"] = nonempty_str(d.get("id"), default="feature-00")
        d["problem"] = nonempty_str(d.get("problem"))
        d["outcome"] = nonempty_str(d.get("outcome"))
        title = str(d.get("title") or "").strip()
        d["title"] = title or derive_title(str(d["problem"]))
        d["scope"] = nonempty_str_list(d.get("scope"))
        slug = str(d.get("slug") or "").strip()
        d["slug"] = slug or slugify(str(d["title"]))

        deps = d.get("dependencies")
        if isinstance(deps, list):
            own = d.get("id")
            seen: list[str] = []
            for dep in deps:
                ds = str(dep)
                if _FEATURE_ID_RE.match(ds) and ds != own and ds not in seen:
                    seen.append(ds)
            d["dependencies"] = seen
        else:
            d["dependencies"] = []
        return d


class FeaturePlanList(BaseModel):
    """Full set of features the generator derived from one PRD."""

    model_config = ConfigDict(strict=False, extra="ignore")

    prd_title: str = Field(default="")
    prd_goal: str = Field(default="")
    features: list[FeaturePlan] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)
        d["prd_title"] = nonempty_str(d.get("prd_title"))
        d["prd_goal"] = nonempty_str(d.get("prd_goal"))
        if not isinstance(d.get("features"), list):
            d["features"] = []
        return d

    @model_validator(mode="after")
    def _dedupe_and_sanitize(self) -> FeaturePlanList:
        seen: set[str] = set()
        kept: list[FeaturePlan] = []
        for f in self.features:
            if f.id in seen:
                logger.warning("[feature_plan] dropping duplicate feature id %s", f.id)
                continue
            seen.add(f.id)
            kept.append(f)
        self.features = kept

        ids = {f.id for f in self.features}
        deps_by_id = {f.id: [d for d in f.dependencies if d in ids] for f in self.features}
        deps_by_id = _strip_back_edges(deps_by_id)
        for f in self.features:
            f.dependencies = deps_by_id.get(f.id, [])
        return self

    def topological_order(self) -> list[FeaturePlan]:
        """Return features in dependency order (a feature follows its deps)."""
        by_id = {f.id: f for f in self.features}
        order_index = {f.id: i for i, f in enumerate(self.features)}
        ordered: list[FeaturePlan] = []
        done: set[str] = set()

        def visit(fid: str) -> None:
            if fid in done:
                return
            for dep in sorted(by_id[fid].dependencies, key=lambda d: order_index[d]):
                visit(dep)
            done.add(fid)
            ordered.append(by_id[fid])

        for f in self.features:
            visit(f.id)
        return ordered
