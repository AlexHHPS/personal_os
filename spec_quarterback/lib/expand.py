"""Phase 2 of the generator: one feature stub -> its SDD document set.

Three staged free-form JSON calls produce the document set in dependency order:

    requirements  ->  design (sees requirements)  ->  tasks (sees both)

Each call embeds the matching skeleton (loaded live) as the target structure and
the upstream document as authoritative context. ``feature_id`` / ``feature_title``
are forced onto every document afterward so the set stays internally consistent
regardless of model drift.
"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from spec_quarterback.lib.constraints import extract_tech_stack, role_system
from spec_quarterback.lib.llm import call_model
from spec_quarterback.lib.prompts.generation import (
    DESIGN_PROMPT,
    DESIGN_ROLE,
    DESIGN_TEMPERATURE,
    REQUIREMENTS_PROMPT,
    REQUIREMENTS_ROLE,
    REQUIREMENTS_TEMPERATURE,
    TASKS_PROMPT,
    TASKS_ROLE,
    TASKS_TEMPERATURE,
)
from spec_quarterback.lib.schemas import (
    Constitution,
    Design,
    FeaturePlan,
    Requirements,
    Tasks,
)
from spec_quarterback.lib.templates_loader import SpecTemplates

logger = logging.getLogger(__name__)

_LAYOUT_UNSPECIFIED = "(unspecified — pick one repository root and use it consistently)"
_DATA_MODEL_NONE = (
    "(none extracted — define each entity once and reuse the exact same entity, "
    "field, and enum names across requirements, design, and tasks)"
)


def _project_structure(constitution: Constitution | None) -> str:
    """The locked repository layout to anchor every file path the feature emits."""
    if constitution is not None:
        layout = (constitution.project_structure or "").strip()
        if layout:
            return layout
    return _LAYOUT_UNSPECIFIED


async def expand_feature(
    *,
    feature: FeaturePlan,
    prd_text: str,
    templates: SpecTemplates,
    client: AsyncOpenAI,
    model: str,
    constitution: Constitution | None = None,
    data_model_context: str = "",
    em_context: str = "",
) -> tuple[Requirements, Design, Tasks]:
    """Expand one feature stub into (requirements, design, tasks).

    ``constitution`` (when present) pins the repository ``project_structure`` into
    every staged prompt so features place files under the same root instead of each
    inventing one that collides with the constitution (a critic STOP blocker).
    ``data_model_context`` (the project's canonical shared data model, rendered by
    ``spec_store.data_model_context``) pins entity/field/enum names so features do
    not each invent a different shape for the same domain table.
    """
    tech_stack = extract_tech_stack(prd_text)
    banned = templates.banned_vocabulary()
    layout = _project_structure(constitution)
    data_model = data_model_context.strip() or _DATA_MODEL_NONE
    feature_json = feature.model_dump_json(indent=2)

    logger.info("[expand] %s: requirements", feature.id)
    req = await call_model(
        client=client,
        model=model,
        system=role_system(em_context, tech_stack, REQUIREMENTS_ROLE),
        user=(
            REQUIREMENTS_PROMPT.replace("{{skeleton}}", templates.requirements_skeleton)
            .replace("{{prd_text}}", prd_text)
            .replace("{{feature_json}}", feature_json)
            .replace("{{data_model}}", data_model)
            .replace("{{project_structure}}", layout)
            .replace("{{banned}}", banned)
        ),
        temperature=REQUIREMENTS_TEMPERATURE,
        schema_cls=Requirements,
    )
    req = req.model_copy(update={"feature_id": feature.id, "feature_title": feature.title})
    req_json = req.model_dump_json(indent=2)

    logger.info("[expand] %s: design", feature.id)
    des = await call_model(
        client=client,
        model=model,
        system=role_system(em_context, tech_stack, DESIGN_ROLE),
        user=(
            DESIGN_PROMPT.replace("{{skeleton}}", templates.design_skeleton)
            .replace("{{requirements_json}}", req_json)
            .replace("{{data_model}}", data_model)
            .replace("{{project_structure}}", layout)
            .replace("{{banned}}", banned)
        ),
        temperature=DESIGN_TEMPERATURE,
        schema_cls=Design,
    )
    des = des.model_copy(update={"feature_id": feature.id, "feature_title": feature.title})

    logger.info("[expand] %s: tasks", feature.id)
    tsk = await call_model(
        client=client,
        model=model,
        system=role_system(em_context, tech_stack, TASKS_ROLE),
        user=(
            TASKS_PROMPT.replace("{{skeleton}}", templates.tasks_skeleton)
            .replace("{{requirements_json}}", req_json)
            .replace("{{design_json}}", des.model_dump_json(indent=2))
            .replace("{{project_structure}}", layout)
            .replace("{{banned}}", banned)
        ),
        temperature=TASKS_TEMPERATURE,
        schema_cls=Tasks,
    )
    tsk = tsk.model_copy(update={"feature_id": feature.id, "feature_title": feature.title})
    return req, des, tsk
