"""Phase 1 of the generator: PRD -> ``FeaturePlanList``.

A single free-form JSON call decomposes the PRD into mid-size feature stubs.
Phase 2 (:mod:`.expand`) then turns each stub into a full document set.
"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from spec_quarterback.lib.constraints import extract_tech_stack, role_system
from spec_quarterback.lib.llm import call_model
from spec_quarterback.lib.prompts.generation import (
    DECOMPOSE_PROMPT,
    DECOMPOSE_ROLE,
    DECOMPOSE_TEMPERATURE,
)
from spec_quarterback.lib.schemas import FeaturePlanList

logger = logging.getLogger(__name__)


async def run_decompose(
    *,
    prd_text: str,
    client: AsyncOpenAI,
    model: str,
    em_context: str = "",
) -> FeaturePlanList:
    """Decompose a PRD into a validated ``FeaturePlanList`` (never raises)."""
    tech_stack = extract_tech_stack(prd_text)
    system = role_system(em_context, tech_stack, DECOMPOSE_ROLE)
    user = DECOMPOSE_PROMPT.replace("{{prd_text}}", prd_text)
    logger.info("[decompose] PRD -> FeaturePlanList")
    return await call_model(
        client=client,
        model=model,
        system=system,
        user=user,
        temperature=DECOMPOSE_TEMPERATURE,
        schema_cls=FeaturePlanList,
    )
