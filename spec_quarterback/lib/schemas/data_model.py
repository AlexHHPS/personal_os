"""``DataModel`` — the PRD-level canonical data model, shared by every feature.

Generated ONCE per PRD (like the constitution is generated once per project) and
fed into every feature's expansion so features reference the SAME entities, field
names, types, and enum values instead of each inventing its own schema. Without
it, the same domain table drifts into incompatible shapes across features (e.g.
``PricingTableRow`` in one feature, ``BaseTariff`` in another) and the features
cannot share a database.

It reuses ``Design``'s :class:`Entity` / :class:`EntityField` shapes so the
canonical model and each feature's ``entity_fields`` are aligned by construction.
No hard validations: optional fields + a ``mode="before"`` healer, consistent
with the rest of the generator schemas.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spec_quarterback.lib.schemas._heal import nonempty_str, str_list
from spec_quarterback.lib.schemas.design import Entity, EntityField


class DataEnum(BaseModel):
    """A closed value set the PRD defines (a status, kind, category, ...)."""

    model_config = ConfigDict(strict=False, extra="ignore")

    name: str = Field(default="")
    values: list[str] = Field(default_factory=list, description="The exact member values.")
    description: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["name"] = nonempty_str(d.get("name"))
        d["values"] = str_list(d.get("values"))
        d["description"] = nonempty_str(d.get("description"), default="")
        return d


class DataModel(BaseModel):
    """The canonical entities/fields/enums every feature of a PRD must share."""

    model_config = ConfigDict(strict=False, extra="ignore")

    prd_slug: str = Field(default="")
    prd_title: str = Field(default="")
    overview: str = Field(default="", description="1-3 sentences on the data model's scope.")
    entities: list[Entity] = Field(default_factory=list)
    entity_fields: list[EntityField] = Field(
        default_factory=list, description="Field rows keyed by entity name."
    )
    enums: list[DataEnum] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)
        d["prd_slug"] = nonempty_str(d.get("prd_slug"), default="")
        d["prd_title"] = nonempty_str(d.get("prd_title"), default="")
        d["overview"] = nonempty_str(d.get("overview"), default="")
        d["relationships"] = str_list(d.get("relationships"))
        for key in ("entities", "entity_fields", "enums"):
            if not isinstance(d.get(key), list):
                d[key] = []
        return d

    def is_empty(self) -> bool:
        """True when there is nothing canonical to share (extraction was a no-op)."""
        return not (self.entities or self.entity_fields or self.enums)

    def fields_for(self, entity: str) -> list[EntityField]:
        return [f for f in self.entity_fields if f.entity == entity]
