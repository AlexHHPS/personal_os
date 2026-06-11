"""``Design`` — the design.md document schema.

Mirrors ``specs/template/skeleton/design.md``. The skeleton's per-entity field
table is hoisted to a flat top-level ``entity_fields`` list keyed by ``entity``
(the store regroups them when rendering), keeping the document a set of flat
lists rather than tables-within-tables. No hard validations: optional fields +
defaults + a ``mode="before"`` healer that coerces drift, so a partial model
response still parses. The critic is the quality gate.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spec_quarterback.lib.schemas._heal import nonempty_str, str_list
from spec_quarterback.lib.schemas.requirements import _heal_status


class Component(BaseModel):
    model_config = ConfigDict(strict=False, extra="ignore")

    name: str = Field(default="")
    responsibility: str = Field(default="", description="Single-sentence responsibility.")
    interface: str = Field(default="", description="Key public methods/endpoints.")
    dependencies: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["name"] = nonempty_str(d.get("name"))
        d["responsibility"] = nonempty_str(d.get("responsibility"))
        d["interface"] = nonempty_str(d.get("interface"), default="")
        d["dependencies"] = str_list(d.get("dependencies"))
        return d


class Entity(BaseModel):
    model_config = ConfigDict(strict=False, extra="ignore")

    name: str = Field(default="")
    description: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["name"] = nonempty_str(d.get("name"))
        d["description"] = nonempty_str(d.get("description"), default="")
        return d


class EntityField(BaseModel):
    """One row of an entity's field table, hoisted flat and keyed by entity."""

    model_config = ConfigDict(strict=False, extra="ignore")

    entity: str = Field(default="", description="Name of the entity this field belongs to.")
    field: str = Field(default="")
    type: str = Field(default="", description="Field type, e.g. UUID, text, timestamptz.")
    constraints: str = Field(default="", description="e.g. PK, NOT NULL, UNIQUE, FK -> X.")
    description: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["entity"] = nonempty_str(d.get("entity"))
        d["field"] = nonempty_str(d.get("field"))
        d["type"] = nonempty_str(d.get("type"))
        d["constraints"] = nonempty_str(d.get("constraints"), default="")
        d["description"] = nonempty_str(d.get("description"), default="")
        return d


class Endpoint(BaseModel):
    model_config = ConfigDict(strict=False, extra="ignore")

    method: str = Field(default="")
    path: str = Field(default="")
    auth: str = Field(default="")
    request_body: str = Field(default="", description="Request schema (JSON-ish string).")
    response: str = Field(default="", description="Success response schema (JSON-ish string).")
    errors: list[str] = Field(default_factory=list, description="Each 'NNN: <payload>'.")

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["method"] = nonempty_str(d.get("method"))
        d["path"] = nonempty_str(d.get("path"))
        d["auth"] = nonempty_str(d.get("auth"), default="")
        d["request_body"] = nonempty_str(d.get("request_body"), default="")
        d["response"] = nonempty_str(d.get("response"), default="")
        d["errors"] = str_list(d.get("errors"))
        return d


class Decision(BaseModel):
    model_config = ConfigDict(strict=False, extra="ignore")

    decision: str = Field(default="")
    alternative: str = Field(default="")
    reason: str = Field(default="", description="Why this choice ('we chose X because Y').")

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["decision"] = nonempty_str(d.get("decision"))
        d["alternative"] = nonempty_str(d.get("alternative"), default="")
        d["reason"] = nonempty_str(d.get("reason"))
        return d


class RiskItem(BaseModel):
    model_config = ConfigDict(strict=False, extra="ignore")

    risk: str = Field(default="")
    mitigation: str = Field(default="")
    area: str = Field(default="", description="Dependency/area the risk attaches to.")

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        d["risk"] = nonempty_str(d.get("risk"))
        d["mitigation"] = nonempty_str(d.get("mitigation"))
        d["area"] = nonempty_str(d.get("area"), default="")
        return d


class Design(BaseModel):
    """The design.md document for one feature."""

    model_config = ConfigDict(strict=False, extra="ignore")

    feature_id: str = Field(default="feature-00")
    feature_title: str = Field(default="")
    status: str = Field(default="Draft")
    architecture_overview: str = Field(default="", description="How this feature fits the system.")
    components: list[Component] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    entity_fields: list[EntityField] = Field(
        default_factory=list, description="Data-model field rows, keyed by entity."
    )
    relationships: list[str] = Field(default_factory=list)
    endpoints: list[Endpoint] = Field(default_factory=list)
    error_handling: str = Field(default="")
    security: str = Field(default="")
    decisions: list[Decision] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)
        d["feature_id"] = nonempty_str(d.get("feature_id"), default="feature-00")
        d["feature_title"] = nonempty_str(d.get("feature_title"))
        d["status"] = _heal_status(d.get("status"))
        d["architecture_overview"] = nonempty_str(d.get("architecture_overview"))
        d["error_handling"] = nonempty_str(d.get("error_handling"), default="")
        d["security"] = nonempty_str(d.get("security"), default="")
        for key in ("relationships", "non_goals"):
            d[key] = str_list(d.get(key))
        for key in ("components", "entities", "entity_fields", "endpoints", "decisions", "risks"):
            if not isinstance(d.get(key), list):
                d[key] = []
        return d
