"""``Tasks`` — the tasks.md document schema.

Mirrors ``specs/template/skeleton/tasks.md``. Each task carries a ``done_when``,
requirement references for traceability, and dependencies. No hard validations:
optional fields + defaults + a ``mode="before"`` healer; the critic is the
quality gate.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spec_quarterback.lib.schemas._heal import nonempty_str, str_list

_ESTIMATES: Final[frozenset[str]] = frozenset({"S", "M", "L"})


class TaskItem(BaseModel):
    model_config = ConfigDict(strict=False, extra="ignore")

    id: str = Field(default="T-00")
    title: str = Field(default="")
    phase: str = Field(default="", description="Phase grouping, e.g. 'Foundation'.")
    requirement_refs: list[str] = Field(
        default_factory=list, description="Referenced US-/EC-/NFR- ids."
    )
    estimate: str = Field(default="M", description="Rough size: S | M | L.")
    implement: str = Field(default="", description="One-line description of the changes.")
    done_when: str = Field(default="", description="Verifiable completion condition.")
    depends_on: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["id"] = nonempty_str(d.get("id"), default="T-00")
        d["title"] = nonempty_str(d.get("title"))
        d["phase"] = nonempty_str(d.get("phase"), default="")
        d["implement"] = nonempty_str(d.get("implement"), default="")
        d["done_when"] = nonempty_str(d.get("done_when"))
        est = str(d.get("estimate") or "").strip().upper()
        d["estimate"] = est if est in _ESTIMATES else "M"
        d["requirement_refs"] = str_list(d.get("requirement_refs"))
        d["depends_on"] = str_list(d.get("depends_on"))
        return d


class Tasks(BaseModel):
    """The tasks.md document for one feature."""

    model_config = ConfigDict(strict=False, extra="ignore")

    feature_id: str = Field(default="feature-00")
    feature_title: str = Field(default="")
    implementation_order: str = Field(default="", description="Note on sequencing.")
    tasks: list[TaskItem] = Field(default_factory=list)
    verification_checklist: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)
        d["feature_id"] = nonempty_str(d.get("feature_id"), default="feature-00")
        d["feature_title"] = nonempty_str(d.get("feature_title"))
        d["implementation_order"] = nonempty_str(d.get("implementation_order"), default="")
        if not isinstance(d.get("tasks"), list) or not d.get("tasks"):
            d["tasks"] = [{"id": "T-00"}]
        d["verification_checklist"] = str_list(d.get("verification_checklist"))
        return d
