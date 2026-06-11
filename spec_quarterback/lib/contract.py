"""Per-feature PRD contract — extract once from the PRD, then reuse.

The fidelity critic needs a checkable record of what the PRD demands for a
feature. This module distils that into a :class:`FeatureContract` and persists it
as ``contract.md`` in the feature folder (mirroring
:func:`lib.constitution.ensure_constitution`). Later refine runs reuse the
persisted — and possibly human-curated — contract instead of re-extracting it.

Resilience: the extraction is a free-form ``call_model`` parsed leniently, and a
missing/empty PRD yields an empty contract (action ``skipped``) so the refiner
simply falls back to the structural-only review rather than failing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from openai import AsyncOpenAI

from spec_quarterback.lib.constraints import extract_tech_stack, role_system
from spec_quarterback.lib.llm import call_model
from spec_quarterback.lib.prompts.generation import (
    CONTRACT_PROMPT,
    CONTRACT_ROLE,
    CONTRACT_TEMPERATURE,
)
from spec_quarterback.lib.schemas import FeatureContract
from spec_quarterback.lib.spec_store import (
    DocKind,
    DocMeta,
    FeatureDoc,
    parse_doc,
    write_doc,
)

logger = logging.getLogger(__name__)


def _read_contract(feature_dir: Path) -> FeatureContract | None:
    path = feature_dir / "contract.md"
    if not path.is_file():
        return None
    try:
        doc = parse_doc(path.read_text(encoding="utf-8"), DocKind.contract)
    except Exception as exc:  # tolerate a corrupt contract; re-extract
        logger.warning("[contract] unreadable %s: %s", path, exc)
        return None
    return doc.model if isinstance(doc.model, FeatureContract) else None


async def extract_contract(
    *,
    feature_id: str,
    feature_title: str,
    anchor: str,
    prd_text: str,
    client: AsyncOpenAI,
    model: str,
    em_context: str = "",
) -> FeatureContract:
    """Distil one feature's PRD requirement inventory from the PRD (never raises)."""
    tech_stack = extract_tech_stack(prd_text)
    feature_json = json.dumps(
        {"id": feature_id, "title": feature_title, "scope": anchor}, indent=2, ensure_ascii=False
    )
    logger.info("[contract] extracting for %s", feature_id)
    contract = await call_model(
        client=client,
        model=model,
        system=role_system(em_context, tech_stack, CONTRACT_ROLE),
        user=(
            CONTRACT_PROMPT.replace("{{prd_text}}", prd_text).replace(
                "{{feature_json}}", feature_json
            )
        ),
        temperature=CONTRACT_TEMPERATURE,
        schema_cls=FeatureContract,
    )
    return contract.model_copy(update={"feature_id": feature_id, "feature_title": feature_title})


async def ensure_contract(
    *,
    feature_dir: Path,
    feature_id: str,
    feature_title: str,
    feature_slug: str,
    anchor: str,
    prd_text: str,
    client: AsyncOpenAI,
    model: str,
    generated_at: str = "",
    em_context: str = "",
) -> tuple[FeatureContract, str]:
    """Return ``(contract, action)`` where action is reused | created | skipped.

    Reads an existing ``contract.md`` if present (and non-empty); otherwise
    extracts from the PRD and persists. An empty/absent PRD yields an empty
    contract with action ``skipped`` (the caller then reviews structurally only).
    """
    existing = _read_contract(feature_dir)
    if existing is not None and existing.items:
        logger.info("[contract] reusing %s", feature_dir / "contract.md")
        return existing, "reused"
    if not prd_text.strip():
        return FeatureContract(feature_id=feature_id, feature_title=feature_title), "skipped"

    contract = await extract_contract(
        feature_id=feature_id,
        feature_title=feature_title,
        anchor=anchor,
        prd_text=prd_text,
        client=client,
        model=model,
        em_context=em_context,
    )
    if not contract.items:
        logger.info("[contract] extraction found no items for %s; skipping persist", feature_id)
        return contract, "skipped"
    meta = DocMeta(
        doc_kind=str(DocKind.contract),
        feature_slug=feature_slug,
        generated_at=generated_at,
    )
    write_doc(FeatureDoc(kind=DocKind.contract, model=contract, meta=meta), feature_dir)
    return contract, "created"
