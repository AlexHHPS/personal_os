"""SDD generator: PRD -> per-feature document sets (two-phase).

Replaces the single-call ``SpecList`` generator. The flow:

1. **constitution-once** — generate ``<specs_root>/constitution.md`` if absent
   (locked, project-level, reused thereafter);
2. **decompose** — one call: PRD -> ``FeaturePlanList`` (the plan);
3. **expand** — per feature, three staged calls produce requirements -> design
   -> tasks; features expand concurrently under a bounded semaphore;
4. **write** — each feature's documents land in its own folder, idempotently;
   the PRD-level ``index.md`` roadmap is rewritten.

All model calls are free-form JSON parsed leniently (:func:`call_model`), so
format drift degrades gracefully rather than aborting the run.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from openai import AsyncOpenAI

from spec_quarterback.lib.constitution import ensure_constitution
from spec_quarterback.lib.contract import ensure_contract
from spec_quarterback.lib.data_model import ensure_data_model
from spec_quarterback.lib.decompose import run_decompose
from spec_quarterback.lib.expand import expand_feature
from spec_quarterback.lib.schemas import (
    Constitution,
    DataModel,
    FeaturePlan,
    FeaturePlanList,
)
from spec_quarterback.lib.spec_store import (
    FeatureDocSet,
    WriteReport,
    data_model_context,
    feature_dir,
    read_prd_dir,
    write_feature_docset,
    write_prd_index,
)
from spec_quarterback.lib.templates_loader import load_templates

logger = logging.getLogger(__name__)

DEFAULT_OMNIROUTE_MODEL = "hermes-combo"
DEFAULT_CONCURRENCY = 3


@dataclass(frozen=True)
class GenerateResult:
    """Outcome of one generation run."""

    feature_plan: FeaturePlanList
    constitution: Constitution
    constitution_action: str  # created | reused
    data_model: DataModel
    data_model_action: str  # created | reused | skipped
    write_report: WriteReport
    docsets: list[FeatureDocSet]
    prd_dir: Path
    specs_root: Path
    affected_project: str
    prd_slug: str
    llm_calls: int
    duration_seconds: float


async def run_generator(
    *,
    prd_text: str,
    prd_slug: str,
    prd_title: str,
    affected_project: str,
    source_prd: str,
    specs_root: Path,
    prd_dir: Path,
    client: AsyncOpenAI,
    model: str = DEFAULT_OMNIROUTE_MODEL,
    em_context: str = "",
    workdir: Path | None = None,
    max_features: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    generated_at: datetime | None = None,
) -> GenerateResult:
    """Generate per-feature SDD document sets from a PRD and write them."""
    started = time.monotonic()
    templates = load_templates(workdir)
    stamp = (generated_at or datetime.now(UTC)).isoformat()

    constitution, con_action = await ensure_constitution(
        specs_root=specs_root,
        prd_text=prd_text,
        project_name=affected_project or prd_title,
        templates=templates,
        client=client,
        model=model,
        generated_at=stamp,
        affected_project=affected_project,
        em_context=em_context,
    )

    # Decompose the PRD and extract the canonical shared data model concurrently —
    # both depend only on the PRD text. The data model is fed into every feature's
    # expansion so features build on one schema instead of each inventing their own.
    plan, (data_model, dm_action) = await asyncio.gather(
        run_decompose(prd_text=prd_text, client=client, model=model, em_context=em_context),
        ensure_data_model(
            prd_dir=prd_dir,
            prd_slug=prd_slug,
            prd_title=prd_title,
            prd_text=prd_text,
            client=client,
            model=model,
            generated_at=stamp,
            affected_project=affected_project,
            em_context=em_context,
        ),
    )
    dm_context = data_model_context(data_model)
    logger.info("[generator] data model %s (%d entities)", dm_action, len(data_model.entities))
    features = plan.topological_order()
    if max_features is not None:
        dropped = len(features) - max_features
        if dropped > 0:
            logger.warning("[generator] capping at %d features (%d dropped)", max_features, dropped)
        features = features[:max_features]

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _contract_created(feature: FeaturePlan) -> bool:
        """Extract + persist this feature's PRD contract, anchored on the PRD-derived
        plan (not the generated spec) so a silently dropped requirement can't hide from
        the fidelity critic. Best-effort: a failure never aborts generation."""
        try:
            anchor = " ".join(
                part
                for part in (feature.problem, feature.outcome, "; ".join(feature.scope or []))
                if part
            )
            _, action = await ensure_contract(
                feature_dir=feature_dir(prd_dir, feature.id, feature.slug),
                feature_id=feature.id,
                feature_title=feature.title,
                feature_slug=feature.slug,
                anchor=anchor,
                prd_text=prd_text,
                client=client,
                model=model,
                generated_at=stamp,
                em_context=em_context,
            )
            return action == "created"
        except Exception as exc:  # contract is best-effort; never kill the run
            logger.warning("[generator] contract extraction failed for %s: %s", feature.id, exc)
            return False

    async def _expand(feature: FeaturePlan) -> tuple[FeaturePlan, tuple, bool]:  # type: ignore[type-arg]
        async with sem:
            docs, contract_created = await asyncio.gather(
                expand_feature(
                    feature=feature,
                    prd_text=prd_text,
                    templates=templates,
                    client=client,
                    model=model,
                    constitution=constitution,
                    data_model_context=dm_context,
                    em_context=em_context,
                ),
                _contract_created(feature),
            )
            return feature, docs, contract_created

    expanded = await asyncio.gather(*[_expand(f) for f in features])

    report = WriteReport(dest_dir=prd_dir)
    for feature, (req, des, tsk), _cc in expanded:
        report.merge(
            write_feature_docset(
                prd_dir=prd_dir,
                feature_id=feature.id,
                feature_slug=feature.slug,
                requirements=req,
                design=des,
                tasks=tsk,
                affected_project=affected_project,
                prd_slug=prd_slug,
                prd_title=plan.prd_title or prd_title,
                prd_goal=plan.prd_goal,
                source_prd=source_prd,
                generated_at=stamp,
            )
        )

    docsets = read_prd_dir(prd_dir)
    write_prd_index(
        prd_dir,
        docsets,
        prd_title=plan.prd_title or prd_title,
        prd_goal=plan.prd_goal,
        affected_project=affected_project,
        generated_at=stamp,
    )

    contracts_created = sum(1 for *_, cc in expanded if cc)
    llm_calls = (
        (1 if con_action == "created" else 0)
        + (1 if dm_action == "created" else 0)
        + 1  # decompose
        + 3 * len(features)
        + contracts_created
    )
    return GenerateResult(
        feature_plan=plan,
        constitution=constitution,
        constitution_action=con_action,
        data_model=data_model,
        data_model_action=dm_action,
        write_report=report,
        docsets=docsets,
        prd_dir=prd_dir,
        specs_root=specs_root,
        affected_project=affected_project,
        prd_slug=prd_slug,
        llm_calls=llm_calls,
        duration_seconds=time.monotonic() - started,
    )
