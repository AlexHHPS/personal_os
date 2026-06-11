"""Pydantic schemas for the spec_quarterback SDD flow.

The flow produces a Spec-Driven-Development document set per feature:

* :class:`FeaturePlan` / :class:`FeaturePlanList` — PRD decomposition (phase 1).
* :class:`Requirements`, :class:`Design`, :class:`Tasks` — the per-feature
  document set (phase 2 expansion).
* :class:`Constitution` — project-level steering, generated once.
* :class:`CriticVerdict` — the refiner's quality verdict (replaces the legacy
  5-dimension ``QualityScore``).

The legacy flat ``Spec`` / ``SpecList`` remain only so the store can still read
pre-rewrite spec files; the generator and refiner no longer produce them.
"""

from spec_quarterback.lib.schemas.constitution import Constitution
from spec_quarterback.lib.schemas.contract import (
    ContractItem,
    FeatureContract,
)
from spec_quarterback.lib.schemas.data_model import DataEnum, DataModel
from spec_quarterback.lib.schemas.design import (
    Component,
    Decision,
    Design,
    Endpoint,
    Entity,
    EntityField,
    RiskItem,
)
from spec_quarterback.lib.schemas.feature_plan import (
    FeaturePlan,
    FeaturePlanList,
)
from spec_quarterback.lib.schemas.requirements import (
    NfrItem,
    OpenQuestion,
    Requirements,
    UserStory,
)
from spec_quarterback.lib.schemas.spec import Spec, SpecList
from spec_quarterback.lib.schemas.tasks import TaskItem, Tasks
from spec_quarterback.lib.schemas.verdict import (
    CRITIC_WEIGHTS,
    CoverageItem,
    CriticVerdict,
)

__all__ = [
    "CRITIC_WEIGHTS",
    "Component",
    "Constitution",
    "ContractItem",
    "CoverageItem",
    "CriticVerdict",
    "DataEnum",
    "DataModel",
    "Decision",
    "Design",
    "Endpoint",
    "Entity",
    "EntityField",
    "FeatureContract",
    "FeaturePlan",
    "FeaturePlanList",
    "NfrItem",
    "OpenQuestion",
    "Requirements",
    "RiskItem",
    "Spec",
    "SpecList",
    "TaskItem",
    "Tasks",
    "UserStory",
]
