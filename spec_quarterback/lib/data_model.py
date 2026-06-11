"""PRD-level canonical data model — extract once from the PRD, then reuse.

Every feature of a PRD shares one data model. This module distils it from the PRD
into a :class:`DataModel` and persists it as ``data-model.md`` in the PRD folder
(alongside ``index.md``), mirroring :func:`lib.constitution.ensure_constitution`
and :func:`lib.contract.ensure_contract`. Later runs reuse the persisted — and
possibly human-curated — model instead of re-extracting it, and the generator
feeds it into every feature's expansion so features build on the same schema.

Resilience: extraction is a free-form ``call_model`` parsed leniently, and a
missing/empty PRD (or an extraction that finds nothing) yields an empty model
with action ``skipped`` so the generator simply expands without a shared model
rather than failing.
"""

from __future__ import annotations

import logging
from pathlib import Path

from openai import AsyncOpenAI

from spec_quarterback.lib.constraints import extract_tech_stack, role_system
from spec_quarterback.lib.llm import call_model
from spec_quarterback.lib.prompts.generation import (
    DATA_MODEL_PROMPT,
    DATA_MODEL_ROLE,
    DATA_MODEL_TEMPERATURE,
)
from spec_quarterback.lib.schemas import DataModel
from spec_quarterback.lib.spec_store import (
    DocKind,
    DocMeta,
    FeatureDoc,
    parse_doc,
    write_doc,
)

logger = logging.getLogger(__name__)


def read_data_model(prd_dir: Path) -> DataModel | None:
    """Read a persisted ``data-model.md`` from the PRD folder, or ``None``."""
    path = prd_dir / "data-model.md"
    if not path.is_file():
        return None
    try:
        doc = parse_doc(path.read_text(encoding="utf-8"), DocKind.data_model)
    except Exception as exc:  # tolerate a corrupt model; re-extract
        logger.warning("[data_model] unreadable %s: %s", path, exc)
        return None
    return doc.model if isinstance(doc.model, DataModel) else None


async def extract_data_model(
    *,
    prd_text: str,
    prd_slug: str,
    prd_title: str,
    client: AsyncOpenAI,
    model: str,
    em_context: str = "",
) -> DataModel:
    """Distil the PRD's canonical shared data model (never raises)."""
    tech_stack = extract_tech_stack(prd_text)
    logger.info("[data_model] extracting canonical model for %s", prd_slug or prd_title)
    dm = await call_model(
        client=client,
        model=model,
        system=role_system(em_context, tech_stack, DATA_MODEL_ROLE),
        user=DATA_MODEL_PROMPT.replace("{{prd_text}}", prd_text),
        temperature=DATA_MODEL_TEMPERATURE,
        schema_cls=DataModel,
    )
    return dm.model_copy(update={"prd_slug": prd_slug, "prd_title": dm.prd_title or prd_title})


async def ensure_data_model(
    *,
    prd_dir: Path,
    prd_slug: str,
    prd_title: str,
    prd_text: str,
    client: AsyncOpenAI,
    model: str,
    generated_at: str = "",
    affected_project: str = "",
    em_context: str = "",
) -> tuple[DataModel, str]:
    """Return ``(data_model, action)`` where action is reused | created | skipped.

    Reads an existing ``data-model.md`` if present and non-empty; otherwise
    extracts from the PRD and persists. An absent/empty PRD — or an extraction
    that surfaces nothing — yields an empty model with action ``skipped`` (the
    generator then expands features without a shared model).
    """
    existing = read_data_model(prd_dir)
    if existing is not None and not existing.is_empty():
        logger.info("[data_model] reusing %s", prd_dir / "data-model.md")
        return existing, "reused"
    if not prd_text.strip():
        return DataModel(prd_slug=prd_slug, prd_title=prd_title), "skipped"

    dm = await extract_data_model(
        prd_text=prd_text,
        prd_slug=prd_slug,
        prd_title=prd_title,
        client=client,
        model=model,
        em_context=em_context,
    )
    if dm.is_empty():
        logger.info("[data_model] extraction found no shared entities; skipping persist")
        return dm, "skipped"

    meta = DocMeta(
        doc_kind=str(DocKind.data_model),
        affected_project=affected_project,
        prd_slug=prd_slug,
        prd_title=prd_title,
        generated_at=generated_at,
    )
    write_doc(FeatureDoc(kind=DocKind.data_model, model=dm, meta=meta), prd_dir)
    return dm, "created"
