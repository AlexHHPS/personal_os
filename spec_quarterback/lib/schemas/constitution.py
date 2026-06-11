"""``Constitution`` — the project-level constitution.md document schema.

Mirrors ``specs/template/skeleton/constitution.md``. Generated ONCE per project
from the PRD's tech-stack section, then locked. No hard validations: optional
fields + defaults + a ``mode="before"`` healer so a partial model response still
parses into a usable steering document.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spec_quarterback.lib.schemas._heal import nonempty_str, str_list


class Constitution(BaseModel):
    """Project steering: stack, principles, standards, boundaries, workflow."""

    model_config = ConfigDict(strict=False, extra="ignore")

    project_name: str = Field(default="")
    product_vision: str = Field(default="", description="1-3 sentences: problem, whom, why.")
    tech_stack: list[str] = Field(default_factory=list, description="Runtime/framework/db/infra.")
    architecture_principles: list[str] = Field(default_factory=list)
    coding_standards: list[str] = Field(default_factory=list)
    project_structure: str = Field(default="")
    commands: list[str] = Field(default_factory=list, description="Build/test/lint/dev commands.")
    boundaries_always: list[str] = Field(default_factory=list)
    boundaries_ask_first: list[str] = Field(default_factory=list)
    boundaries_never: list[str] = Field(default_factory=list)
    git_workflow: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)
        d["project_name"] = nonempty_str(d.get("project_name"))
        d["product_vision"] = nonempty_str(d.get("product_vision"))
        d["project_structure"] = nonempty_str(d.get("project_structure"), default="")
        d["tech_stack"] = str_list(d.get("tech_stack")) or ["(unspecified)"]
        for key in (
            "architecture_principles",
            "coding_standards",
            "commands",
            "boundaries_always",
            "boundaries_ask_first",
            "boundaries_never",
            "git_workflow",
        ):
            d[key] = str_list(d.get(key))
        return d
