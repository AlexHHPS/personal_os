"""Improve step — rewrite one document to resolve the critic's issues for it.

Targeted: the refiner improves only the documents whose failing dimensions map
to them (``CriticVerdict.target_docs``), passing just that document's issues.
Parsed leniently so a drifted rewrite never crashes the loop.
"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI
from pydantic import BaseModel

from spec_quarterback.lib.constraints import role_system
from spec_quarterback.lib.llm import call_model
from spec_quarterback.lib.prompts.refinement import (
    IMPROVE_PROMPT,
    IMPROVE_ROLE,
    IMPROVE_TEMPERATURE,
)
from spec_quarterback.lib.schemas import (
    CriticVerdict,
    Design,
    Requirements,
    Tasks,
)
from spec_quarterback.lib.templates_loader import SpecTemplates

logger = logging.getLogger(__name__)

_DOC_SCHEMA: dict[str, type[BaseModel]] = {
    "requirements": Requirements,
    "design": Design,
    "tasks": Tasks,
}

# The authoritative sibling each doc must stay consistent with when rewritten, so an
# improve pass can't re-introduce schema/route/file drift the generator avoided
# (e.g. tasks.md inventing a column set different from design.md).
_CONSISTENCY_SIBLINGS: dict[str, tuple[str, ...]] = {
    "requirements": (),
    "design": ("requirements",),
    "tasks": ("design", "requirements"),
}


def _skeleton_for(doc_name: str, templates: SpecTemplates) -> str:
    return {
        "requirements": templates.requirements_skeleton,
        "design": templates.design_skeleton,
        "tasks": templates.tasks_skeleton,
    }.get(doc_name, "")


def _consistency_block(
    doc_name: str,
    context_docs: dict[str, BaseModel] | None,
    data_model_context: str,
) -> str:
    """Render the canonical data model + authoritative sibling docs as a drift anchor."""
    parts: list[str] = []
    dm = (data_model_context or "").strip()
    if dm:
        parts += [
            "## Canonical data model (use these EXACT entity / field / enum names and types)",
            "",
            dm,
            "",
        ]
    for sibling in _CONSISTENCY_SIBLINGS.get(doc_name, ()):
        model = (context_docs or {}).get(sibling)
        if model is not None:
            parts += [
                f"## {sibling}.md (authoritative — match its entity names, fields, types, "
                "endpoints, and file paths)",
                "",
                model.model_dump_json(indent=2),
                "",
            ]
    return "\n".join(parts).strip() or "(no additional consistency anchors)"


def _format_issues(verdict: CriticVerdict, doc_name: str) -> str:
    lines: list[str] = []
    for issue in verdict.issues_for(doc_name):
        suggestion = f" -> {issue.suggestion}" if issue.suggestion else ""
        loc = f" ({issue.location})" if issue.location else ""
        lines.append(
            f"- [{issue.severity}] {issue.dimension}{loc}: {issue.description}{suggestion}"
        )
    # PRD coverage gaps are requirement-level: surface them (with the PRD text) to the
    # requirements/design editors so a dropped or contradicted requirement is restored, and
    # surface INVENTED scope so the editor removes what the PRD never asked for.
    if doc_name in ("requirements", "design"):
        for gap in verdict.coverage_gaps():
            ref = f" [PRD: {gap.prd_ref}]" if gap.prd_ref else ""
            detail = gap.statement or gap.note or "(see PRD)"
            lines.append(f"- [PRD {gap.status}] {gap.contract_id}{ref}: {detail}")
        for inv in verdict.invented_scope():
            ref = f" [PRD: {inv.prd_ref}]" if inv.prd_ref else ""
            detail = inv.statement or inv.note or "(not in the PRD)"
            lines.append(f"- [PRD INVENTED] {inv.contract_id}{ref}: {detail}")
    for term in verdict.banned_vocabulary:
        lines.append(f"- [BANNED WORD] '{term.word}' at {term.location}: {term.required_action}")
    for fix in verdict.fix_priority:
        lines.append(f"- (priority) {fix}")
    if verdict.binary_gate.blockers_failed:
        lines.append("- BLOCKERS: " + "; ".join(verdict.binary_gate.blockers_failed))
    return "\n".join(lines) if lines else f"- General: {verdict.summary or 'raise overall quality'}"


async def improve_doc(
    *,
    doc_name: str,
    model: BaseModel,
    verdict: CriticVerdict,
    templates: SpecTemplates,
    client: AsyncOpenAI,
    model_name: str,
    tech_stack: str,
    em_context: str = "",
    context_docs: dict[str, BaseModel] | None = None,
    data_model_context: str = "",
) -> BaseModel:
    """Rewrite one document (``requirements``|``design``|``tasks``) per the critic.

    ``context_docs`` (the other docs in the set) and ``data_model_context`` (the
    canonical shared schema) are rendered as consistency anchors so the rewrite keeps
    entity/field/type/endpoint/path names aligned instead of drifting from the rest of
    the set — the dominant cross-document defect class in review.
    """
    schema = _DOC_SCHEMA[doc_name]
    user = (
        IMPROVE_PROMPT.replace("{{doc_kind}}", doc_name)
        .replace("{{skeleton}}", _skeleton_for(doc_name, templates))
        .replace("{{consistency}}", _consistency_block(doc_name, context_docs, data_model_context))
        .replace("{{doc_json}}", model.model_dump_json(indent=2))
        .replace("{{issues}}", _format_issues(verdict, doc_name))
    )
    logger.info("[improve] rewriting %s", doc_name)
    improved = await call_model(
        client=client,
        model=model_name,
        system=role_system(em_context, tech_stack, IMPROVE_ROLE),
        user=user,
        temperature=IMPROVE_TEMPERATURE,
        schema_cls=schema,
    )
    return improved.model_copy(
        update={
            "feature_id": getattr(model, "feature_id", ""),
            "feature_title": getattr(model, "feature_title", ""),
        }
    )
