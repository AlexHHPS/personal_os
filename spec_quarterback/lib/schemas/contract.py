"""``FeatureContract`` / ``ContractItem`` — the PRD requirement inventory.

For drift detection the refiner needs a checkable record of what the PRD
*demands* for one feature. :func:`contract.extract_contract` distills that from
the PRD into a ``FeatureContract`` — a flat list of atomic, PRD-cited claims —
which is persisted as ``contract.md`` and fed to the fidelity critic so it can
mark each item COVERED / PARTIAL / MISSING / CONTRADICTED against the spec.

Same resilience contract as the other generator schemas (see
:mod:`.feature_plan`): NO hard validation — every field is optional with a
default and ``mode="before"`` healers coerce the common model mistakes. A
near-miss is healed into something usable; the critic, not Pydantic, is the gate.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spec_quarterback.lib.schemas._heal import nonempty_str

_KINDS: Final[frozenset[str]] = frozenset(
    {"functional", "business_rule", "data", "nfr", "role", "formula", "constraint"}
)
_PRIORITIES: Final[frozenset[str]] = frozenset({"MUST", "SHOULD"})


class ContractItem(BaseModel):
    """One atomic requirement the PRD imposes on a feature."""

    model_config = ConfigDict(strict=False, extra="ignore")

    # kind ∈ functional | business_rule | data | nfr | role | formula | constraint
    id: str = Field(default="", description="Stable id, e.g. 'RQ-01'.")
    kind: str = Field(default="functional")
    statement: str = Field(default="", description="What the PRD demands.")
    prd_ref: str = Field(default="", description="PRD section it comes from.")
    priority: str = Field(default="MUST", description="MUST | SHOULD")

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)
        d["id"] = nonempty_str(d.get("id"), default="RQ-00")
        d["statement"] = nonempty_str(d.get("statement"))
        d["prd_ref"] = nonempty_str(d.get("prd_ref"), default="")
        kind = str(d.get("kind") or "").strip().lower()
        d["kind"] = kind if kind in _KINDS else "functional"
        prio = str(d.get("priority") or "").strip().upper()
        d["priority"] = prio if prio in _PRIORITIES else "MUST"
        return d


class FeatureContract(BaseModel):
    """The PRD requirement inventory for one feature (the fidelity ground truth)."""

    model_config = ConfigDict(strict=False, extra="ignore")

    feature_id: str = Field(default="feature-00")
    feature_title: str = Field(default="")
    items: list[ContractItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)
        d["feature_id"] = nonempty_str(d.get("feature_id"), default="feature-00")
        d["feature_title"] = nonempty_str(d.get("feature_title"), default="")
        if not isinstance(d.get("items"), list):
            d["items"] = []
        return d

    @model_validator(mode="after")
    def _dedupe_ids(self) -> FeatureContract:
        seen: set[str] = set()
        kept: list[ContractItem] = []
        for i, item in enumerate(self.items):
            iid = item.id if item.id and item.id != "RQ-00" else f"RQ-{i + 1:02d}"
            if iid in seen:
                iid = f"{iid}-{i + 1}"
            item.id = iid
            seen.add(iid)
            kept.append(item)
        self.items = kept
        return self

    def must_items(self) -> list[ContractItem]:
        return [i for i in self.items if i.priority == "MUST"]
