"""Critic review — assemble a feature's document set and score it.

The critic *system prompt* is loaded live from
``specs/template/critic/spec_quality_reviewer_prompt.md`` (the templates loader);
this module only assembles the document set into the user message and parses the
verdict. The verdict is parsed leniently (:func:`parse_model`) from a free-form
JSON response, so a drifted response degrades to a default verdict rather than
crashing the refiner.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from openai import AsyncOpenAI
from pydantic import BaseModel

from spec_quarterback.lib.json_extract import parse_model
from spec_quarterback.lib.llm import call_freeform
from spec_quarterback.lib.schemas import (
    Constitution,
    CriticVerdict,
    FeatureContract,
)
from spec_quarterback.lib.spec_store import (
    DocKind,
    DocMeta,
    FeatureDoc,
    constitution_body,
    render_body,
)
from spec_quarterback.lib.templates_loader import SpecTemplates

logger = logging.getLogger(__name__)

REVIEW_TEMPERATURE = 0.0
_VERDICT_ORDER = {"STOP": 0, "REVISE": 1, "GO": 2}


def _assemble(
    requirements: BaseModel,
    design: BaseModel,
    tasks: BaseModel,
    constitution: Constitution | None,
    data_model_ctx: str = "",
) -> str:
    parts = ["# SPEC UNDER REVIEW", ""]
    if constitution is not None:
        parts += ["## constitution.md", "", constitution_body(constitution), ""]
    if data_model_ctx.strip():
        parts += [
            "## data-model.md (CANONICAL shared entities — every feature must use these "
            "exact entity/field/enum names)",
            "",
            data_model_ctx.strip(),
            "",
        ]
    parts += [
        "## requirements.md",
        "",
        render_body(FeatureDoc(DocKind.requirements, requirements, DocMeta())),
        "",
        "## design.md",
        "",
        render_body(FeatureDoc(DocKind.design, design, DocMeta())),
        "",
        "## tasks.md",
        "",
        render_body(FeatureDoc(DocKind.tasks, tasks, DocMeta())),
        "",
    ]
    return "\n".join(parts)


def _assemble_fidelity(
    requirements: BaseModel,
    design: BaseModel,
    tasks: BaseModel,
    contract: FeatureContract,
) -> str:
    items = (
        "\n".join(
            f"- [{i.id}] ({i.priority}/{i.kind}) {i.statement}"
            + (f"  [PRD: {i.prd_ref}]" if i.prd_ref else "")
            for i in contract.items
        )
        or "(no contract items)"
    )
    return "\n".join(
        [
            "# CONTRACT — the PRD requirements this feature MUST honour",
            "",
            items,
            "",
            "# SPEC UNDER REVIEW",
            "",
            "## requirements.md",
            "",
            render_body(FeatureDoc(DocKind.requirements, requirements, DocMeta())),
            "",
            "## design.md",
            "",
            render_body(FeatureDoc(DocKind.design, design, DocMeta())),
            "",
            "## tasks.md",
            "",
            render_body(FeatureDoc(DocKind.tasks, tasks, DocMeta())),
            "",
        ]
    )


async def review_structural(
    *,
    requirements: BaseModel,
    design: BaseModel,
    tasks: BaseModel,
    constitution: Constitution | None,
    templates: SpecTemplates,
    client: AsyncOpenAI,
    model: str,
    feature_label: str = "",
    data_model_context: str = "",
) -> CriticVerdict:
    """Score a feature's document set on the 8 internal-quality dimensions.

    When ``data_model_context`` is supplied (the project's canonical shared data
    model), the critic can flag this feature for drifting from the canonical
    entity/field/enum names — a cross-feature consistency defect.
    """
    user = _assemble(requirements, design, tasks, constitution, data_model_context)
    logger.info("[critic] reviewing %s", feature_label or "feature")
    raw = await call_freeform(
        client=client,
        model=model,
        system=templates.critic_prompt,
        user=user,
        temperature=REVIEW_TEMPERATURE,
    )
    return parse_model(raw, CriticVerdict)


async def review_fidelity(
    *,
    requirements: BaseModel,
    design: BaseModel,
    tasks: BaseModel,
    contract: FeatureContract,
    templates: SpecTemplates,
    client: AsyncOpenAI,
    model: str,
    feature_label: str = "",
) -> CriticVerdict:
    """Score the spec's fidelity to the PRD contract (coverage + faithfulness)."""
    user = _assemble_fidelity(requirements, design, tasks, contract)
    logger.info("[critic] fidelity-checking %s", feature_label or "feature")
    raw = await call_freeform(
        client=client,
        model=model,
        system=templates.fidelity_prompt,
        user=user,
        temperature=REVIEW_TEMPERATURE,
    )
    return parse_model(raw, CriticVerdict)


def _combine_verdict(a: str, b: str) -> str:
    """STOP beats REVISE beats GO."""
    return min((a, b), key=lambda v: _VERDICT_ORDER.get(v, 1))


def _merge_verdicts(structural: CriticVerdict, fidelity: CriticVerdict) -> CriticVerdict:
    """Fold the fidelity verdict into the structural one — a single unified verdict.

    The fidelity pass owns the ``prd_*`` dimensions and the ``coverage`` map; the gate
    is the AND of both gates (a fidelity gap can't pass while still allowing improve
    to run, because the merged verdict stays REVISE rather than STOP).
    """
    data = structural.model_dump(mode="json")
    fdata = fidelity.model_dump(mode="json")
    scores = dict(data.get("scores") or {})
    scores.update(fdata.get("scores") or {})
    merged = {
        **data,
        "scores": scores,
        "binary_gate": {
            "passed": structural.binary_gate.passed and fidelity.binary_gate.passed,
            "blockers_failed": [
                *structural.binary_gate.blockers_failed,
                *fidelity.binary_gate.blockers_failed,
            ],
        },
        "issues": [*(data.get("issues") or []), *(fdata.get("issues") or [])],
        "coverage": fdata.get("coverage") or [],
        "verdict": _combine_verdict(structural.verdict, fidelity.verdict),
        "summary": " ".join(s for s in (structural.summary, fidelity.summary) if s).strip(),
    }
    return CriticVerdict.model_validate(merged)


async def review_docset(
    *,
    requirements: BaseModel,
    design: BaseModel,
    tasks: BaseModel,
    constitution: Constitution | None,
    templates: SpecTemplates,
    client: AsyncOpenAI,
    model: str,
    feature_label: str = "",
    contract: FeatureContract | None = None,
    data_model_context: str = "",
) -> CriticVerdict:
    """Review a feature's document set.

    With a non-empty ``contract``, the structural and PRD-fidelity critics run
    concurrently and their verdicts are merged; otherwise only the structural
    critic runs (today's behaviour). ``data_model_context`` (the canonical shared
    data model) lets the structural critic flag cross-feature schema drift.
    ``reviewed_at`` is stamped here from the wall clock — the model has no clock
    and otherwise hallucinates a date.
    """
    if contract is not None and contract.items:
        structural, fidelity = await asyncio.gather(
            review_structural(
                requirements=requirements,
                design=design,
                tasks=tasks,
                constitution=constitution,
                templates=templates,
                client=client,
                model=model,
                feature_label=feature_label,
                data_model_context=data_model_context,
            ),
            review_fidelity(
                requirements=requirements,
                design=design,
                tasks=tasks,
                contract=contract,
                templates=templates,
                client=client,
                model=model,
                feature_label=feature_label,
            ),
        )
        verdict = _merge_verdicts(structural, fidelity)
    else:
        verdict = await review_structural(
            requirements=requirements,
            design=design,
            tasks=tasks,
            constitution=constitution,
            templates=templates,
            client=client,
            model=model,
            feature_label=feature_label,
            data_model_context=data_model_context,
        )
    return verdict.model_copy(update={"reviewed_at": datetime.now(UTC).isoformat()})
