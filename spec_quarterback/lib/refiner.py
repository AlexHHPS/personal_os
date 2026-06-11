"""Critic-driven refinement loop — raise each feature's doc-set to the bar.

For each feature document set the refiner runs:

    review -> [improve targeted docs -> review] x N

stopping when the weighted score reaches the quality bar with the binary gate
passed, when an iteration stops improving (convergence), or at ``max_iters``.
A STOP verdict does NOT abort the loop — its blockers are fed to the improve step
so the spec can climb out of STOP over iterations and across nightly runs (the
generator is a one-off bootstrap; this refiner grinds each spec upward toward the
bar night after night). The improve step rewrites only the documents whose failing
dimensions map to them. ``locked`` documents are never rewritten; a feature whose
documents are all locked is skipped. The best-scoring version seen is always the
one kept, so an iteration that regresses is never persisted.

Verdicts and score history are written to each feature's ``review.md`` and the
PRD-level ``index.md`` is re-rendered with the latest verdicts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import frontmatter
from openai import AsyncOpenAI
from pydantic import BaseModel

from spec_quarterback.lib.constraints import extract_tech_stack
from spec_quarterback.lib.contract import ensure_contract
from spec_quarterback.lib.critic import review_docset
from spec_quarterback.lib.data_model import read_data_model
from spec_quarterback.lib.generator import (
    DEFAULT_CONCURRENCY,
    DEFAULT_OMNIROUTE_MODEL,
)
from spec_quarterback.lib.improve import improve_doc
from spec_quarterback.lib.schemas import Constitution, CriticVerdict
from spec_quarterback.lib.spec_store import (
    DocKind,
    DocMeta,
    FeatureDoc,
    FeatureDocSet,
    data_model_context,
    read_constitution,
    read_prd_dir,
    write_doc,
    write_prd_index,
    write_review,
)
from spec_quarterback.lib.templates_loader import SpecTemplates, load_templates

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERS = 3
DEFAULT_QUALITY_BAR = 0.9
DEFAULT_MIN_IMPROVEMENT = 0.01


class StopReason:
    bar_met = "bar_met"
    converged = "converged"
    max_iters = "max_iters"
    locked = "locked"


@dataclass(frozen=True)
class RefineResult:
    feature_id: str
    verdict: CriticVerdict
    iterations: int
    score_history: list[float]
    verdict_history: list[str]
    stop_reason: str


@dataclass
class RefineRunResult:
    prd_dir: Path
    results: dict[str, RefineResult] = field(default_factory=dict)
    skipped_locked: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


_DOC_NAMES = ("requirements", "design", "tasks")


def _docs_by_name(docset: FeatureDocSet) -> dict[str, FeatureDoc]:
    return {
        "requirements": docset.requirements,  # type: ignore[dict-item]
        "design": docset.design,  # type: ignore[dict-item]
        "tasks": docset.tasks,  # type: ignore[dict-item]
    }


def _persist(
    docset: FeatureDocSet,
    models: dict[str, BaseModel],
    verdict: CriticVerdict,
    *,
    score_history: list[float],
    verdict_history: list[str],
    iterations: int,
    locked: dict[str, bool],
) -> None:
    by_name = _docs_by_name(docset)
    ref_meta = next((d.meta for d in by_name.values() if d is not None), DocMeta())
    if iterations > 0:
        for name, model in models.items():
            doc = by_name.get(name)
            if doc is None or locked.get(name, False):
                continue
            meta = replace(doc.meta, iteration=doc.meta.iteration + iterations)
            write_doc(FeatureDoc(kind=DocKind(name), model=model, meta=meta), docset.feature_dir)
    review_meta = DocMeta(
        doc_kind=str(DocKind.review),
        feature_slug=docset.feature_slug,
        prd_slug=ref_meta.prd_slug,
        generated_at=ref_meta.generated_at,
        iteration=iterations,
    )
    write_review(
        docset.feature_dir,
        verdict,
        score_history=score_history,
        verdict_history=verdict_history,
        meta=review_meta,
    )


async def refine_feature(
    *,
    docset: FeatureDocSet,
    constitution: Constitution | None,
    prd_text: str,
    templates: SpecTemplates,
    client: AsyncOpenAI,
    model: str,
    em_context: str = "",
    max_iters: int = DEFAULT_MAX_ITERS,
    quality_bar: float = DEFAULT_QUALITY_BAR,
    min_improvement: float = DEFAULT_MIN_IMPROVEMENT,
    fidelity: bool = True,
    data_model_ctx: str = "",
) -> RefineResult | None:
    """Refine one feature's document set; write it back. None if incomplete."""
    by_name = _docs_by_name(docset)
    if any(by_name[n] is None for n in _DOC_NAMES):
        logger.warning("[refiner] %s missing a document; skipping", docset.feature_id)
        return None

    locked = {n: by_name[n].meta.locked for n in _DOC_NAMES}
    if all(locked.values()):
        logger.info("[refiner] %s fully locked; skipping", docset.feature_id)
        existing = docset.review.verdict if docset.review else CriticVerdict()
        return RefineResult(docset.feature_id, existing, 0, [], [], StopReason.locked)

    models: dict[str, BaseModel] = {n: by_name[n].model for n in _DOC_NAMES}
    tech_stack = extract_tech_stack(prd_text)

    # PRD contract for the fidelity pass (extracted once, reused). Skipped when
    # fidelity is off or the PRD is unavailable -> structural-only review.
    contract = None
    if fidelity:
        req_model = models["requirements"]
        anchor = " ".join(
            part
            for part in (
                str(getattr(req_model, "overview", "") or ""),
                "; ".join(getattr(req_model, "in_scope", []) or []),
            )
            if part
        )
        contract, action = await ensure_contract(
            feature_dir=docset.feature_dir,
            feature_id=docset.feature_id,
            feature_title=docset.feature_title,
            feature_slug=docset.feature_slug,
            anchor=anchor,
            prd_text=prd_text,
            client=client,
            model=model,
            generated_at=by_name["requirements"].meta.generated_at,
            em_context=em_context,
        )
        logger.info(
            "[refiner] %s contract %s (%d items)", docset.feature_id, action, len(contract.items)
        )

    async def _review(current: dict[str, BaseModel]) -> CriticVerdict:
        return await review_docset(
            requirements=current["requirements"],
            design=current["design"],
            tasks=current["tasks"],
            constitution=constitution,
            templates=templates,
            client=client,
            model=model,
            feature_label=docset.feature_id,
            contract=contract,
            data_model_context=data_model_ctx,
        )

    verdict = await _review(models)
    score_history = [verdict.weighted_score]
    verdict_history = [verdict.verdict]
    best_models = dict(models)
    best_verdict = verdict
    iterations = 0

    # A STOP verdict does NOT short-circuit the loop: its blockers are surfaced to the
    # improve step (see improve._format_issues), so the spec can climb out of STOP over
    # iterations and across nightly runs. We stop only on the reachable bar (score+gate),
    # on convergence (improvement stalled), or at max_iters.
    if best_verdict.bar_met(quality_bar):
        stop_reason = StopReason.bar_met
    else:
        stop_reason = StopReason.max_iters
        for _ in range(max_iters):
            targets = [t for t in verdict.target_docs() if not locked.get(t, False)]
            for t in targets:
                models[t] = await improve_doc(
                    doc_name=t,
                    model=models[t],
                    verdict=verdict,
                    templates=templates,
                    client=client,
                    model_name=model,
                    tech_stack=tech_stack,
                    em_context=em_context,
                    context_docs=models,
                    data_model_context=data_model_ctx,
                )
            verdict = await _review(models)
            iterations += 1
            score_history.append(verdict.weighted_score)
            verdict_history.append(verdict.verdict)

            gain = verdict.weighted_score - best_verdict.weighted_score
            if gain > 0:
                best_models = dict(models)
                best_verdict = verdict

            if best_verdict.bar_met(quality_bar):
                stop_reason = StopReason.bar_met
                break
            if gain < min_improvement:
                stop_reason = StopReason.converged
                break

    _persist(
        docset,
        best_models,
        best_verdict,
        score_history=score_history,
        verdict_history=verdict_history,
        iterations=iterations,
        locked=locked,
    )
    logger.info(
        "[refiner] %s -> %s score %.3f after %d iter(s) (%s)",
        docset.feature_id,
        best_verdict.verdict,
        best_verdict.weighted_score,
        iterations,
        stop_reason,
    )
    return RefineResult(
        docset.feature_id, best_verdict, iterations, score_history, verdict_history, stop_reason
    )


def _prd_text_from_docsets(docsets: list[FeatureDocSet]) -> str:
    for ds in docsets:
        for doc in (ds.requirements, ds.design, ds.tasks):
            if doc is not None and doc.meta.source_prd:
                path = Path(doc.meta.source_prd).expanduser()
                if path.is_file():
                    return str(frontmatter.loads(path.read_text(encoding="utf-8")).content)
                return ""
    return ""


def _index_meta(docsets: list[FeatureDocSet]) -> tuple[str, str, str, str]:
    for ds in docsets:
        for doc in (ds.requirements, ds.design, ds.tasks):
            if doc is not None:
                m = doc.meta
                return m.prd_title, m.prd_goal, m.affected_project, m.generated_at
    return "Specs", "", "", ""


async def refine_specs(
    *,
    prd_dir: Path,
    omniroute_endpoint: str,
    omniroute_api_key: str | None = None,
    omniroute_model: str = DEFAULT_OMNIROUTE_MODEL,
    workdir: Path | None = None,
    em_context: str = "",
    max_iters: int = DEFAULT_MAX_ITERS,
    quality_bar: float = DEFAULT_QUALITY_BAR,
    concurrency: int = DEFAULT_CONCURRENCY,
    fidelity: bool = True,
) -> RefineRunResult:
    """Refine every feature doc-set under ``prd_dir`` against the critic.

    With ``fidelity`` on (default), each feature is also checked against a PRD
    contract (``contract.md``, extracted once) so the loop detects and corrects
    drift from the PRD; off restores the structural-only review.
    """
    started = time.monotonic()
    docsets = read_prd_dir(prd_dir)
    prd_text = _prd_text_from_docsets(docsets)
    constitution = read_constitution(prd_dir.parent)
    data_model = read_data_model(prd_dir)
    data_model_ctx = data_model_context(data_model) if data_model is not None else ""
    templates = load_templates(workdir)

    client = AsyncOpenAI(base_url=omniroute_endpoint, api_key=omniroute_api_key or "not-needed")
    run = RefineRunResult(prd_dir=prd_dir)
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _refine(ds: FeatureDocSet) -> RefineResult | None:
        async with sem:
            return await refine_feature(
                docset=ds,
                constitution=constitution,
                prd_text=prd_text,
                templates=templates,
                client=client,
                model=omniroute_model,
                em_context=em_context,
                max_iters=max_iters,
                quality_bar=quality_bar,
                fidelity=fidelity,
                data_model_ctx=data_model_ctx,
            )

    try:
        results = await asyncio.gather(*[_refine(ds) for ds in docsets])
    finally:
        await client.close()

    for result in results:
        if result is None:
            continue
        run.results[result.feature_id] = result
        if result.stop_reason == StopReason.locked:
            run.skipped_locked.append(result.feature_id)

    refreshed = read_prd_dir(prd_dir)
    prd_title, prd_goal, affected_project, generated_at = _index_meta(refreshed)
    write_prd_index(
        prd_dir,
        refreshed,
        prd_title=prd_title,
        prd_goal=prd_goal,
        affected_project=affected_project,
        generated_at=generated_at,
    )
    run.duration_seconds = time.monotonic() - started
    return run
