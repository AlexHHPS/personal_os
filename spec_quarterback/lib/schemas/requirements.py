"""``Requirements`` — the requirements.md document schema.

Mirrors ``specs/template/skeleton/requirements.md`` section-for-section so the
generated document fills the structure the critic looks for (Gherkin acceptance
criteria, an explicit Out of Scope section, enumerated edge cases, numeric
NFRs). No hard validations: every field is optional with a default and the
``mode="before"`` healer coerces drift so a partial/garbled model response still
parses into a usable document. The critic is the quality gate, not Pydantic.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spec_quarterback.lib.schemas._heal import (
    nonempty_str,
    nonempty_str_list,
    str_list,
)

_STATUSES: Final[frozenset[str]] = frozenset({"Draft", "Reviewed", "Approved"})


def _heal_status(value: object) -> str:
    text = str(value or "").strip().title()
    return text if text in _STATUSES else "Draft"


class UserStory(BaseModel):
    """One INVEST user story with Gherkin acceptance criteria."""

    model_config = ConfigDict(strict=False, extra="ignore")

    id: str = Field(default="US-00")
    title: str = Field(default="")
    as_a: str = Field(default="", description="Role: 'As a <role>'.")
    i_want: str = Field(default="", description="Action: 'I want to <action>'.")
    so_that: str = Field(default="", description="Value: 'So that <outcome>'.")
    acceptance_criteria: list[str] = Field(
        default_factory=list, description="Each in 'GIVEN ... WHEN ... THEN ...' form."
    )

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["id"] = nonempty_str(d.get("id"), default="US-00")
        for key in ("title", "as_a", "i_want", "so_that"):
            d[key] = nonempty_str(d.get(key))
        d["acceptance_criteria"] = nonempty_str_list(d.get("acceptance_criteria"))
        return d


class NfrItem(BaseModel):
    """One non-functional requirement, expressed numerically where possible."""

    model_config = ConfigDict(strict=False, extra="ignore")

    category: str = Field(default="", description="e.g. performance, security, accessibility.")
    requirement: str = Field(default="", description="The measurable requirement (numbers).")

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["category"] = nonempty_str(d.get("category"))
        d["requirement"] = nonempty_str(d.get("requirement"))
        return d


class OpenQuestion(BaseModel):
    """An unresolved question with an owner and due date (critic requirement)."""

    model_config = ConfigDict(strict=False, extra="ignore")

    question: str = Field(default="")
    owner: str = Field(default="(unassigned)")
    due: str = Field(default="(undated)")

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["question"] = nonempty_str(d.get("question"))
        d["owner"] = nonempty_str(d.get("owner"), default="(unassigned)")
        d["due"] = nonempty_str(d.get("due"), default="(undated)")
        return d


class Requirements(BaseModel):
    """The requirements.md document for one feature."""

    model_config = ConfigDict(strict=False, extra="ignore")

    feature_id: str = Field(default="feature-00")
    feature_title: str = Field(default="")
    status: str = Field(default="Draft", description="Draft | Reviewed | Approved.")
    overview: str = Field(default="", description="2-4 sentences: what, what problem, why now.")
    outcomes: list[str] = Field(default_factory=list, description="Measurable DoD outcomes.")
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list, description="What will NOT be built.")
    user_stories: list[UserStory] = Field(default_factory=list)
    edge_cases: list[str] = Field(
        default_factory=list, description="Failure/boundary scenarios, each 'EC-NN: <behavior>'."
    )
    nfrs: list[NfrItem] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(
        default_factory=list, description="Empty list means all resolved."
    )

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)
        d["feature_id"] = nonempty_str(d.get("feature_id"), default="feature-00")
        d["feature_title"] = nonempty_str(d.get("feature_title"))
        d["status"] = _heal_status(d.get("status"))
        d["overview"] = nonempty_str(d.get("overview"))
        d["outcomes"] = nonempty_str_list(d.get("outcomes"))
        d["in_scope"] = nonempty_str_list(d.get("in_scope"))
        d["out_of_scope"] = nonempty_str_list(d.get("out_of_scope"), default="(none declared)")
        if not isinstance(d.get("user_stories"), list) or not d.get("user_stories"):
            d["user_stories"] = [{"id": "US-00"}]
        d["edge_cases"] = str_list(d.get("edge_cases"))
        if not isinstance(d.get("nfrs"), list):
            d["nfrs"] = []
        if not isinstance(d.get("open_questions"), list):
            d["open_questions"] = []
        return d
