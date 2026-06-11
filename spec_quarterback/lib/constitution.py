"""Project constitution: generate once per project, then reuse (locked).

The first PRD for a project generates ``<specs_root>/constitution.md`` from the
PRD's declared tech stack and product intent; every later PRD reuses it. It is
written ``locked: true`` (human-owned steering) and never regenerated — its
existence is the lock.
"""

from __future__ import annotations

import logging
from pathlib import Path

from openai import AsyncOpenAI

from spec_quarterback.lib.constraints import extract_tech_stack, role_system
from spec_quarterback.lib.llm import call_model
from spec_quarterback.lib.prompts.generation import (
    CONSTITUTION_PROMPT,
    CONSTITUTION_ROLE,
    CONSTITUTION_TEMPERATURE,
)
from spec_quarterback.lib.schemas import Constitution
from spec_quarterback.lib.spec_store import read_constitution, write_constitution
from spec_quarterback.lib.templates_loader import SpecTemplates

logger = logging.getLogger(__name__)


async def ensure_constitution(
    *,
    specs_root: Path,
    prd_text: str,
    project_name: str,
    templates: SpecTemplates,
    client: AsyncOpenAI,
    model: str,
    generated_at: str,
    affected_project: str,
    em_context: str = "",
) -> tuple[Constitution, str]:
    """Return ``(constitution, action)`` where action is reused | created.

    Reads an existing locked constitution if present; otherwise generates one
    from the PRD's tech stack and writes it locked.
    """
    existing = read_constitution(specs_root)
    if existing is not None:
        logger.info("[constitution] reusing %s", specs_root)
        return existing, "reused"

    tech_stack = extract_tech_stack(prd_text)
    logger.info("[constitution] generating once for %s", project_name)
    con = await call_model(
        client=client,
        model=model,
        system=role_system(em_context, tech_stack, CONSTITUTION_ROLE),
        user=(
            CONSTITUTION_PROMPT.replace("{{skeleton}}", templates.constitution_skeleton)
            .replace("{{project_name}}", project_name)
            .replace("{{tech_stack}}", tech_stack)
            .replace("{{prd_text}}", prd_text)
        ),
        temperature=CONSTITUTION_TEMPERATURE,
        schema_cls=Constitution,
    )
    if not con.project_name.strip() or con.project_name == "(unspecified)":
        con = con.model_copy(update={"project_name": project_name})
    write_constitution(
        specs_root,
        con,
        affected_project=affected_project,
        generated_at=generated_at,
        locked=True,
    )
    return con, "created"
