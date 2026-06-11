"""Markdown store for the SDD document set.

A PRD decomposes into features; each feature is a folder holding its document
set:

    <prd_dir>/
      index.md                     roadmap of features + latest verdicts
      feature-01-<slug>/
        requirements.md  design.md  tasks.md  review.md
      feature-02-<slug>/ ...

and the project-level constitution lives one level up at
``<specs_root>/constitution.md``.

Each file's YAML front-matter is the round-trippable source of truth (the full
typed document plus store metadata); the markdown body is a human-readable
rendering derived from it. Idempotency uses a 16-char ``generated_hash`` per
file: re-running the generator skips a file whose generation is unchanged
(preserving any refinement since) and never overwrites a ``locked: true`` file.

Resilience: reads tolerate malformed files (skipped with a warning) and the
lenient schemas never reject drifted content, so a single bad document cannot
abort a run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import frontmatter
from pydantic import BaseModel

from spec_quarterback.lib.schemas import (
    Constitution,
    CriticVerdict,
    DataModel,
    Design,
    FeatureContract,
    Requirements,
    Tasks,
)
from spec_quarterback.lib.text import slugify

logger = logging.getLogger(__name__)

__all__ = [
    "DocKind",
    "DocMeta",
    "FeatureDoc",
    "FeatureDocSet",
    "ReviewDoc",
    "WriteAction",
    "WriteEntry",
    "WriteReport",
    "constitution_body",
    "constitution_path",
    "content_hash",
    "data_model_context",
    "feature_dir",
    "list_feature_dirs",
    "parse_doc",
    "read_constitution",
    "read_feature_docset",
    "read_prd_dir",
    "read_review",
    "render_body",
    "render_doc",
    "slugify",
    "write_constitution",
    "write_doc",
    "write_feature_docset",
    "write_prd_index",
    "write_review",
]

_FEATURE_DIR_RE = re.compile(r"^(feature-[0-9]+)-(.*)$")


class DocKind(StrEnum):
    requirements = "requirements"
    design = "design"
    tasks = "tasks"
    review = "review"
    constitution = "constitution"
    contract = "contract"
    data_model = "data_model"


_FILENAME: dict[DocKind, str] = {
    DocKind.requirements: "requirements.md",
    DocKind.design: "design.md",
    DocKind.tasks: "tasks.md",
    DocKind.review: "review.md",
    DocKind.constitution: "constitution.md",
    DocKind.contract: "contract.md",
    DocKind.data_model: "data-model.md",
}

_SCHEMA: dict[DocKind, type[BaseModel]] = {
    DocKind.requirements: Requirements,
    DocKind.design: Design,
    DocKind.tasks: Tasks,
    DocKind.constitution: Constitution,
    DocKind.contract: FeatureContract,
    DocKind.data_model: DataModel,
}

# Store-owned front-matter keys (everything else is document content). These
# deliberately do NOT include the document models' own fields (feature_id,
# feature_title, status, ...), which round-trip through the model.
_META_KEYS: frozenset[str] = frozenset(
    {
        "doc_kind",
        "feature_slug",
        "affected_project",
        "prd_slug",
        "prd_title",
        "prd_goal",
        "source_prd",
        "generated_at",
        "iteration",
        "locked",
        "content_hash",
        "generated_hash",
        # review-only
        "score_history",
        "verdict_history",
    }
)


def content_hash(model: BaseModel) -> str:
    """Deterministic 16-char hash over a document model's content."""
    canonical = json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class DocMeta:
    """Store-owned metadata persisted alongside a document in front-matter."""

    doc_kind: str = ""
    feature_slug: str = ""
    affected_project: str = ""
    prd_slug: str = ""
    prd_title: str = ""
    prd_goal: str = ""
    source_prd: str = ""
    generated_at: str = ""
    iteration: int = 0
    locked: bool = False
    generated_hash: str = ""


@dataclass(frozen=True)
class FeatureDoc:
    """One document (requirements/design/tasks) plus its store metadata."""

    kind: DocKind
    model: BaseModel
    meta: DocMeta

    @property
    def content_hash(self) -> str:
        return content_hash(self.model)

    def filename(self) -> str:
        return _FILENAME[self.kind]

    @property
    def feature_id(self) -> str:
        return str(getattr(self.model, "feature_id", ""))


@dataclass(frozen=True)
class ReviewDoc:
    """A critic verdict plus its score/verdict history for one feature."""

    verdict: CriticVerdict
    score_history: list[float] = field(default_factory=list)
    verdict_history: list[str] = field(default_factory=list)
    meta: DocMeta = field(default_factory=DocMeta)


@dataclass
class FeatureDocSet:
    """The unit the refiner reads and writes: a feature's documents."""

    feature_id: str
    feature_slug: str
    feature_dir: Path
    requirements: FeatureDoc | None = None
    design: FeatureDoc | None = None
    tasks: FeatureDoc | None = None
    review: ReviewDoc | None = None
    contract: FeatureDoc | None = None

    @property
    def feature_title(self) -> str:
        for doc in (self.requirements, self.design, self.tasks):
            if doc is not None:
                title = str(getattr(doc.model, "feature_title", ""))
                if title:
                    return title
        return self.feature_slug

    def docs(self) -> dict[str, FeatureDoc]:
        out: dict[str, FeatureDoc] = {}
        if self.requirements is not None:
            out["requirements"] = self.requirements
        if self.design is not None:
            out["design"] = self.design
        if self.tasks is not None:
            out["tasks"] = self.tasks
        return out


class WriteAction(StrEnum):
    created = "created"
    updated = "updated"
    unchanged = "unchanged"
    locked = "locked"


@dataclass(frozen=True)
class WriteEntry:
    doc_id: str
    path: Path
    action: WriteAction


@dataclass
class WriteReport:
    dest_dir: Path
    entries: list[WriteEntry] = field(default_factory=list)

    def _ids(self, action: WriteAction) -> list[str]:
        return [e.doc_id for e in self.entries if e.action is action]

    @property
    def created(self) -> list[str]:
        return self._ids(WriteAction.created)

    @property
    def updated(self) -> list[str]:
        return self._ids(WriteAction.updated)

    @property
    def unchanged(self) -> list[str]:
        return self._ids(WriteAction.unchanged)

    @property
    def locked(self) -> list[str]:
        return self._ids(WriteAction.locked)

    def merge(self, other: WriteReport) -> None:
        self.entries.extend(other.entries)


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "_none_"


def _checkboxes(items: list[str]) -> str:
    return "\n".join(f"- [ ] {x}" for x in items) if items else "_none_"


def _render_requirements_body(m: Requirements, meta: DocMeta) -> str:
    lines = [
        f"# {m.feature_title or m.feature_id} — Requirements",
        "",
        f"> feature: **{m.feature_id}** · status: **{m.status}** · "
        f"iteration: **{meta.iteration}**",
        "",
        "## 1. Overview & Context",
        m.overview or "_none_",
        "",
        "## 2. Outcomes (Definition of Done)",
        _bullets(m.outcomes),
        "",
        "## 3. Scope",
        "### In Scope",
        _bullets(m.in_scope),
        "",
        "### Out of Scope",
        _bullets(m.out_of_scope),
        "",
        "## 4. User Stories & Acceptance Criteria",
        "",
    ]
    for us in m.user_stories:
        lines += [
            f"### {us.id}: {us.title}",
            f"**As a** {us.as_a} **I want to** {us.i_want} **So that** {us.so_that}",
            "",
            "**Acceptance Criteria:**",
            _checkboxes(us.acceptance_criteria),
            "",
        ]
    nfr_lines = (
        "\n".join(f"- **{n.category}:** {n.requirement}" for n in m.nfrs) if m.nfrs else "_none_"
    )
    if m.open_questions:
        oq = "\n".join(
            f"- {q.question} — Owner: {q.owner} — Due: {q.due}" for q in m.open_questions
        )
    else:
        oq = "All resolved."
    lines += [
        "## 5. Edge Cases & Error Scenarios",
        _bullets(m.edge_cases),
        "",
        "## 6. Non-Functional Requirements",
        nfr_lines,
        "",
        "## 7. Open Questions",
        oq,
    ]
    return "\n".join(lines)


def _render_design_body(m: Design, meta: DocMeta) -> str:
    lines = [
        f"# {m.feature_title or m.feature_id} — Technical Design",
        "",
        f"> feature: **{m.feature_id}** · status: **{m.status}**",
        "",
        "## 1. Architecture Overview",
        m.architecture_overview or "_none_",
        "",
        "## 2. Component Design",
    ]
    if m.components:
        for c in m.components:
            deps = ", ".join(c.dependencies) or "—"
            lines += [
                f"### {c.name}",
                f"- Responsibility: {c.responsibility}",
                f"- Interface: {c.interface or '—'}",
                f"- Dependencies: {deps}",
                "",
            ]
    else:
        lines += ["_none_", ""]

    lines += ["## 3. Data Model", ""]
    entity_names = [e.name for e in m.entities] + [
        f.entity for f in m.entity_fields if f.entity not in {e.name for e in m.entities}
    ]
    seen: set[str] = set()
    ordered_entities: list[str] = []
    for name in entity_names:
        if name not in seen:
            seen.add(name)
            ordered_entities.append(name)
    if ordered_entities:
        for name in ordered_entities:
            desc = next((e.description for e in m.entities if e.name == name), "")
            rows = [f for f in m.entity_fields if f.entity == name]
            lines += [f"### Entity: {name}", desc or "", ""]
            lines += ["| Field | Type | Constraints | Description |", "|---|---|---|---|"]
            if rows:
                for r in rows:
                    con = r.constraints or "—"
                    dsc = r.description or "—"
                    lines.append(f"| {r.field} | {r.type} | {con} | {dsc} |")
            else:
                lines.append("| _none_ | | | |")
            lines.append("")
    else:
        lines += ["_none_", ""]
    lines += ["### Relationships", _bullets(m.relationships), ""]

    lines += ["## 4. API / Interface Contracts", ""]
    if m.endpoints:
        for e in m.endpoints:
            errs = "; ".join(e.errors) or "—"
            lines += [
                f"### {e.method} {e.path}",
                f"- Auth: {e.auth or '—'}",
                f"- Request: {e.request_body or '—'}",
                f"- Response: {e.response or '—'}",
                f"- Errors: {errs}",
                "",
            ]
    else:
        lines += ["_none_", ""]

    decisions = (
        "\n".join(
            f"| {d.decision} | {d.alternative or '—'} | {d.reason or '—'} |" for d in m.decisions
        )
        if m.decisions
        else "| _none_ | | |"
    )
    risks = (
        "\n".join(f"| {r.area or r.risk} | {r.risk} | {r.mitigation} |" for r in m.risks)
        if m.risks
        else "| _none_ | | |"
    )
    lines += [
        "## 5. Error Handling Strategy",
        m.error_handling or "_none_",
        "",
        "## 6. Security Considerations",
        m.security or "_none_",
        "",
        "## 7. Technical Decisions & Rationale",
        "| Decision | Alternative | Reason |",
        "|---|---|---|",
        decisions,
        "",
        "## 8. Non-Goals (Technical)",
        _bullets(m.non_goals),
        "",
        "## 9. Dependencies & Risks",
        "| Area | Risk | Mitigation |",
        "|---|---|---|",
        risks,
    ]
    return "\n".join(lines)


def _render_tasks_body(m: Tasks, meta: DocMeta) -> str:
    lines = [
        f"# {m.feature_title or m.feature_id} — Tasks",
        "",
        f"> feature: **{m.feature_id}**",
        "",
        "## Implementation Order & Dependency Map",
        m.implementation_order or "_none_",
        "",
        "## Tasks",
        "",
    ]
    phases: list[str] = []
    for t in m.tasks:
        if t.phase and t.phase not in phases:
            phases.append(t.phase)
    grouped: list[tuple[str, list[Any]]]
    if phases:
        grouped = [(p, [t for t in m.tasks if t.phase == p]) for p in phases]
        no_phase = [t for t in m.tasks if not t.phase]
        if no_phase:
            grouped.append(("Other", no_phase))
    else:
        grouped = [("", list(m.tasks))]
    for phase_name, items in grouped:
        if phase_name:
            lines += [f"### {phase_name}", ""]
        for t in items:
            refs = ", ".join(t.requirement_refs) or "—"
            deps = f" (depends on {', '.join(t.depends_on)})" if t.depends_on else ""
            lines += [
                f"- [ ] {t.id}: {t.title} — REQ: {refs} — Est: {t.estimate}{deps}",
                f"  - Implement: {t.implement or '—'}",
                f"  - Done when: {t.done_when or '—'}",
            ]
        lines.append("")
    lines += ["## Verification Checklist", _checkboxes(m.verification_checklist)]
    return "\n".join(lines)


def _render_constitution_body(m: Constitution) -> str:
    return "\n".join(
        [
            f"# {m.project_name or '(project)'} — Constitution / Steering",
            "",
            "## Product Vision",
            m.product_vision or "_none_",
            "",
            "## Tech Stack",
            _bullets(m.tech_stack),
            "",
            "## Architecture Principles",
            _bullets(m.architecture_principles),
            "",
            "## Coding Standards",
            _bullets(m.coding_standards),
            "",
            "## Project Structure",
            m.project_structure or "_none_",
            "",
            "## Commands",
            _bullets(m.commands),
            "",
            "## Boundaries (Three-Tier System)",
            "### ✅ Always",
            _bullets(m.boundaries_always),
            "",
            "### ⚠️ Ask first",
            _bullets(m.boundaries_ask_first),
            "",
            "### 🚫 Never",
            _bullets(m.boundaries_never),
            "",
            "## Git Workflow",
            _bullets(m.git_workflow),
        ]
    )


def _render_contract_body(m: FeatureContract, meta: DocMeta) -> str:
    rows = (
        "\n".join(
            f"| {i.id} | {i.kind} | {i.priority} | {i.statement} | {i.prd_ref or '—'} |"
            for i in m.items
        )
        or "| _none_ | | | | |"
    )
    return "\n".join(
        [
            f"# {m.feature_title or m.feature_id} — PRD Contract",
            "",
            f"> feature: **{m.feature_id}** · items: **{len(m.items)}** "
            f"(MUST: {len(m.must_items())})",
            "",
            "The PRD requirements this feature must honour. The fidelity critic checks the spec "
            "against each item (COVERED / PARTIAL / MISSING / CONTRADICTED). Edit this file to "
            "curate the ground truth — the refiner reuses it.",
            "",
            "| ID | Kind | Priority | Requirement | PRD Ref |",
            "|---|---|---|---|---|",
            rows,
        ]
    )


def _render_data_model_body(m: DataModel, meta: DocMeta) -> str:
    entity_rows = (
        "\n".join(f"| {e.name} | {e.description or '—'} |" for e in m.entities)
        or "| _none_ | |"
    )
    field_rows = (
        "\n".join(
            f"| {f.entity} | {f.field} | {f.type or '—'} | {f.constraints or '—'} "
            f"| {f.description or '—'} |"
            for f in m.entity_fields
        )
        or "| _none_ | | | | |"
    )
    enum_rows = (
        "\n".join(
            f"| {en.name} | {' / '.join(en.values) or '—'} | {en.description or '—'} |"
            for en in m.enums
        )
        or "| _none_ | | |"
    )
    return "\n".join(
        [
            f"# {m.prd_title or m.prd_slug or 'Project'} — Canonical Data Model",
            "",
            "> Shared across every feature of this PRD. Each feature must use these exact "
            "entity, field, and enum names. Edit this file to curate the ground truth — the "
            "generator reuses it.",
            "",
            m.overview or "",
            "",
            "## Entities",
            "| Entity | Description |",
            "|---|---|",
            entity_rows,
            "",
            "## Fields",
            "| Entity | Field | Type | Constraints | Description |",
            "|---|---|---|---|---|",
            field_rows,
            "",
            "## Enums",
            "| Enum | Values | Description |",
            "|---|---|---|",
            enum_rows,
            "",
            "## Relationships",
            _bullets(m.relationships),
        ]
    )


def _render_review_body(
    verdict: CriticVerdict, score_history: list[float], verdict_history: list[str]
) -> str:
    score_rows = "\n".join(
        f"| {dim} | {ds.score:.2f} |" for dim, ds in verdict.scores.items()
    ) or "| _none_ | |"
    issue_rows = (
        "\n".join(
            f"| {i.id or '—'} | {i.severity} | {i.dimension} | {i.description} |"
            for i in verdict.issues
        )
        if verdict.issues
        else "| _none_ | | | |"
    )
    history = (
        " → ".join(f"{s:.2f}" for s in score_history) if score_history else "—"
    )
    coverage_rows = (
        "\n".join(
            f"| {c.contract_id or '—'} | {c.status} | {c.note or c.evidence or '—'} |"
            for c in verdict.coverage
        )
        if verdict.coverage
        else "| _none_ | | |"
    )
    coverage_summary = verdict.coverage_summary()
    return "\n".join(
        [
            f"# Review — verdict: **{verdict.verdict}** · score: "
            f"**{verdict.weighted_score:.3f}** · "
            f"gate: **{'pass' if verdict.passed_gate else 'fail'}**",
            "",
            f"> confidence: {verdict.confidence} · score history: {history}",
            "",
            "## Summary",
            verdict.summary or "_none_",
            "",
            "## Dimension Scores",
            "| Dimension | Score |",
            "|---|---|",
            score_rows,
            "",
            "## Issues",
            "| ID | Severity | Dimension | Description |",
            "|---|---|---|---|",
            issue_rows,
            "",
            "## PRD Coverage",
            f"_{coverage_summary}_" if coverage_summary else "_(fidelity pass not run)_",
            "",
            "| Contract | Status | Note |",
            "|---|---|---|",
            coverage_rows,
            "",
            "## Fix Priority",
            _bullets(verdict.fix_priority),
            "",
            "## Binary Gate",
            _bullets(verdict.binary_gate.blockers_failed) if not verdict.passed_gate else "Passed.",
        ]
    )


_BODY = {
    DocKind.requirements: lambda m, meta: _render_requirements_body(cast(Requirements, m), meta),
    DocKind.design: lambda m, meta: _render_design_body(cast(Design, m), meta),
    DocKind.tasks: lambda m, meta: _render_tasks_body(cast(Tasks, m), meta),
    DocKind.contract: lambda m, meta: _render_contract_body(cast(FeatureContract, m), meta),
    DocKind.data_model: lambda m, meta: _render_data_model_body(cast(DataModel, m), meta),
}


# ---------------------------------------------------------------------------
# Render / parse a document
# ---------------------------------------------------------------------------


def _front_matter(model: BaseModel, meta: DocMeta) -> dict[str, Any]:
    fm: dict[str, Any] = dict(model.model_dump(mode="json"))
    fm.update(
        {
            "doc_kind": str(meta.doc_kind),
            "feature_slug": meta.feature_slug,
            "affected_project": meta.affected_project,
            "prd_slug": meta.prd_slug,
            "prd_title": meta.prd_title,
            "prd_goal": meta.prd_goal,
            "source_prd": meta.source_prd,
            "generated_at": meta.generated_at,
            "iteration": meta.iteration,
            "locked": meta.locked,
            "generated_hash": meta.generated_hash,
            "content_hash": content_hash(model),
        }
    )
    return fm


def render_doc(doc: FeatureDoc) -> str:
    """Render a requirements/design/tasks document to markdown."""
    body = _BODY[doc.kind](doc.model, doc.meta)
    post = frontmatter.Post(content=body, **_front_matter(doc.model, doc.meta))
    return cast(str, frontmatter.dumps(post)) + "\n"


def render_body(doc: FeatureDoc) -> str:
    """Render just the human-readable body of a doc (no front-matter).

    Used to assemble the document set the critic reviews.
    """
    return _BODY[doc.kind](doc.model, doc.meta)


def constitution_body(model: Constitution) -> str:
    """Render the constitution body (no front-matter) for critic context."""
    return _render_constitution_body(model)


def data_model_context(model: DataModel) -> str:
    """Compact canonical-data-model text for the expand prompts and the critic.

    Returns ``""`` when the model is empty, so callers can fall back to today's
    behaviour (no shared model). Lists every entity with its fields, then enums
    and relationships — terse, name-first, so the model anchors on exact names.
    """
    if model.is_empty():
        return ""
    descriptions = {e.name: e.description for e in model.entities}
    fields_by_entity: dict[str, list[Any]] = {}
    for f in model.entity_fields:
        fields_by_entity.setdefault(f.entity, []).append(f)
    # Union of entity names from the entity list and any field-only entities,
    # order-preserving, so a field whose entity was omitted still shows up.
    names = list(dict.fromkeys([e.name for e in model.entities] + list(fields_by_entity)))

    lines: list[str] = []
    if model.overview:
        lines += [model.overview, ""]
    lines.append("Entities & fields:")
    for name in names:
        desc = descriptions.get(name, "")
        lines.append(f"- {name}" + (f": {desc}" if desc else ""))
        for f in fields_by_entity.get(name, []):
            type_part = f" ({f.type})" if f.type else ""
            constraint_part = f" [{f.constraints}]" if f.constraints else ""
            lines.append(f"    - {f.field}{type_part}{constraint_part}")
    if model.enums:
        lines.append("Enums:")
        for en in model.enums:
            lines.append(f"- {en.name}: {' | '.join(en.values)}".rstrip())
    if model.relationships:
        lines.append("Relationships:")
        lines += [f"- {r}" for r in model.relationships]
    return "\n".join(lines).strip()


def _meta_from_fm(fm: dict[str, Any], kind: DocKind) -> DocMeta:
    return DocMeta(
        doc_kind=str(fm.get("doc_kind", str(kind))),
        feature_slug=str(fm.get("feature_slug", "")),
        affected_project=str(fm.get("affected_project", "")),
        prd_slug=str(fm.get("prd_slug", "")),
        prd_title=str(fm.get("prd_title", "")),
        prd_goal=str(fm.get("prd_goal", "")),
        source_prd=str(fm.get("source_prd", "")),
        generated_at=str(fm.get("generated_at", "")),
        iteration=int(fm.get("iteration", 0) or 0),
        locked=bool(fm.get("locked", False)),
        generated_hash=str(fm.get("generated_hash", "")),
    )


def parse_doc(text: str, kind: DocKind) -> FeatureDoc:
    """Parse a requirements/design/tasks markdown file back into a FeatureDoc."""
    post = frontmatter.loads(text)
    fm: dict[str, Any] = dict(post.metadata)
    model_fields = {k: v for k, v in fm.items() if k not in _META_KEYS}
    model = _SCHEMA[kind].model_validate(model_fields)
    return FeatureDoc(kind=kind, model=model, meta=_meta_from_fm(fm, kind))


# ---------------------------------------------------------------------------
# Filesystem: feature doc-set
# ---------------------------------------------------------------------------


def feature_dir(prd_dir: Path, feature_id: str, feature_slug: str) -> Path:
    return prd_dir / f"{feature_id}-{feature_slug}"


def _parse_feature_dirname(name: str) -> tuple[str, str]:
    m = _FEATURE_DIR_RE.match(name)
    if m:
        return m.group(1), m.group(2)
    return name, ""


def write_doc(doc: FeatureDoc, target_dir: Path) -> Path:
    """Write a single document to ``target_dir`` (used by the refiner)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / doc.filename()
    path.write_text(render_doc(doc), encoding="utf-8")
    return path


def _write_doc_idempotent(
    target_dir: Path, kind: DocKind, model: BaseModel, meta_template: DocMeta
) -> WriteEntry:
    path = target_dir / _FILENAME[kind]
    new_hash = content_hash(model)
    feature_id = str(getattr(model, "feature_id", "")) or meta_template.prd_slug
    doc_id = f"{feature_id}/{kind}"

    if path.exists():
        prior: FeatureDoc | None
        try:
            prior = parse_doc(path.read_text(encoding="utf-8"), kind)
        except Exception:  # a corrupt file shouldn't abort the run
            prior = None
        if prior is not None:
            if prior.meta.locked:
                return WriteEntry(doc_id, path, WriteAction.locked)
            prior_gen = prior.meta.generated_hash or content_hash(prior.model)
            if prior_gen == new_hash:
                return WriteEntry(doc_id, path, WriteAction.unchanged)
        action = WriteAction.updated
    else:
        action = WriteAction.created

    meta = replace(meta_template, doc_kind=str(kind), iteration=0, generated_hash=new_hash)
    write_doc(FeatureDoc(kind=kind, model=model, meta=meta), target_dir)
    return WriteEntry(doc_id, path, action)


def write_feature_docset(
    *,
    prd_dir: Path,
    feature_id: str,
    feature_slug: str,
    requirements: Requirements,
    design: Design,
    tasks: Tasks,
    affected_project: str,
    prd_slug: str,
    prd_title: str,
    prd_goal: str,
    source_prd: str,
    generated_at: str,
) -> WriteReport:
    """Write a feature's requirements/design/tasks idempotently per file."""
    target = feature_dir(prd_dir, feature_id, feature_slug)
    meta_template = DocMeta(
        feature_slug=feature_slug,
        affected_project=affected_project,
        prd_slug=prd_slug,
        prd_title=prd_title,
        prd_goal=prd_goal,
        source_prd=source_prd,
        generated_at=generated_at,
    )
    report = WriteReport(dest_dir=target)
    report.entries.append(
        _write_doc_idempotent(target, DocKind.requirements, requirements, meta_template)
    )
    report.entries.append(_write_doc_idempotent(target, DocKind.design, design, meta_template))
    report.entries.append(_write_doc_idempotent(target, DocKind.tasks, tasks, meta_template))
    return report


def read_feature_docset(target_dir: Path) -> FeatureDocSet:
    """Read a feature folder's documents (tolerant of missing/corrupt files)."""
    feature_id, feature_slug = _parse_feature_dirname(target_dir.name)

    def _read(kind: DocKind) -> FeatureDoc | None:
        path = target_dir / _FILENAME[kind]
        if not path.is_file():
            return None
        try:
            return parse_doc(path.read_text(encoding="utf-8"), kind)
        except Exception as exc:  # skip a corrupt doc, keep the rest
            logger.warning("[store] skipping unreadable %s: %s", path, exc)
            return None

    review = None
    review_path = target_dir / _FILENAME[DocKind.review]
    if review_path.is_file():
        try:
            review = read_review(review_path)
        except Exception as exc:  # tolerate a corrupt review file
            logger.warning("[store] skipping unreadable %s: %s", review_path, exc)

    reqs = _read(DocKind.requirements)
    if reqs is not None and reqs.meta.feature_slug:
        feature_slug = feature_slug or reqs.meta.feature_slug
    return FeatureDocSet(
        feature_id=feature_id,
        feature_slug=feature_slug,
        feature_dir=target_dir,
        requirements=reqs,
        design=_read(DocKind.design),
        tasks=_read(DocKind.tasks),
        review=review,
        contract=_read(DocKind.contract),
    )


def list_feature_dirs(prd_dir: Path) -> list[Path]:
    if not prd_dir.is_dir():
        return []
    return sorted(p for p in prd_dir.glob("feature-*") if p.is_dir())


def read_prd_dir(prd_dir: Path) -> list[FeatureDocSet]:
    """Read every feature doc-set under ``prd_dir`` (skips non-feature files)."""
    dirs = list_feature_dirs(prd_dir)
    if not dirs and prd_dir.is_dir() and any(prd_dir.glob("spec-*.md")):
        logger.warning(
            "[store] %s holds legacy flat spec-*.md files and no feature-*/ folders; "
            "re-run the generator to migrate to the SDD doc-set layout",
            prd_dir,
        )
    return [read_feature_docset(d) for d in dirs]


# ---------------------------------------------------------------------------
# Constitution (project-level, generated once)
# ---------------------------------------------------------------------------


def constitution_path(specs_root: Path) -> Path:
    return specs_root / _FILENAME[DocKind.constitution]


def write_constitution(
    specs_root: Path,
    constitution: Constitution,
    *,
    affected_project: str,
    generated_at: str,
    locked: bool = True,
) -> Path:
    specs_root.mkdir(parents=True, exist_ok=True)
    fm: dict[str, Any] = dict(constitution.model_dump(mode="json"))
    fm.update(
        {
            "doc_kind": str(DocKind.constitution),
            "affected_project": affected_project,
            "generated_at": generated_at,
            "locked": locked,
            "content_hash": content_hash(constitution),
        }
    )
    post = frontmatter.Post(content=_render_constitution_body(constitution), **fm)
    path = constitution_path(specs_root)
    path.write_text(cast(str, frontmatter.dumps(post)) + "\n", encoding="utf-8")
    return path


def read_constitution(specs_root: Path) -> Constitution | None:
    path = constitution_path(specs_root)
    if not path.is_file():
        return None
    try:
        post = frontmatter.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # tolerate a corrupt constitution file
        logger.warning("[store] unreadable constitution %s: %s", path, exc)
        return None
    fm = {k: v for k, v in dict(post.metadata).items() if k not in _META_KEYS}
    return Constitution.model_validate(fm)


# ---------------------------------------------------------------------------
# Review (critic verdict + history)
# ---------------------------------------------------------------------------


def write_review(
    target_dir: Path,
    verdict: CriticVerdict,
    *,
    score_history: list[float],
    verdict_history: list[str],
    meta: DocMeta,
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    fm: dict[str, Any] = dict(verdict.model_dump(mode="json"))
    fm.update(
        {
            "doc_kind": str(DocKind.review),
            "feature_slug": meta.feature_slug,
            "prd_slug": meta.prd_slug,
            "generated_at": meta.generated_at,
            "iteration": meta.iteration,
            "score_history": score_history,
            "verdict_history": verdict_history,
        }
    )
    body = _render_review_body(verdict, score_history, verdict_history)
    post = frontmatter.Post(content=body, **fm)
    path = target_dir / _FILENAME[DocKind.review]
    path.write_text(cast(str, frontmatter.dumps(post)) + "\n", encoding="utf-8")
    return path


def read_review(path: Path) -> ReviewDoc:
    post = frontmatter.loads(path.read_text(encoding="utf-8"))
    fm: dict[str, Any] = dict(post.metadata)
    verdict = CriticVerdict.model_validate(fm)  # extra keys ignored
    score_history = [float(x) for x in fm.get("score_history", []) if _is_number(x)]
    verdict_history = [str(x) for x in fm.get("verdict_history", [])]
    return ReviewDoc(
        verdict=verdict,
        score_history=score_history,
        verdict_history=verdict_history,
        meta=_meta_from_fm(fm, DocKind.review),
    )


def _is_number(x: object) -> bool:
    try:
        float(x)  # type: ignore[arg-type]
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# PRD-level index
# ---------------------------------------------------------------------------


def render_prd_index(
    docsets: list[FeatureDocSet],
    *,
    prd_title: str,
    prd_goal: str,
    affected_project: str,
    generated_at: str,
) -> str:
    lines = [
        f"# Specs — {prd_title}",
        "",
        f"> project: **{affected_project}** · generated: {generated_at} · "
        f"features: **{len(docsets)}**",
        "",
        f"**Goal:** {prd_goal}",
        "",
        "| # | Feature | Verdict | Score | Gate | Coverage |",
        "|---|---------|---------|-------|------|----------|",
    ]
    for ds in docsets:
        verdict = ds.review.verdict.verdict if ds.review else "—"
        score = f"{ds.review.verdict.weighted_score:.2f}" if ds.review else "—"
        gate = "—"
        coverage = "—"
        if ds.review:
            gate = "pass" if ds.review.verdict.passed_gate else "fail"
            cov = ds.review.verdict.coverage
            if cov:
                covered = sum(1 for c in cov if c.status == "COVERED")
                coverage = f"{covered}/{len(cov)}"
        link = f"[{ds.feature_title}]({ds.feature_dir.name}/requirements.md)"
        lines.append(
            f"| {ds.feature_id} | {link} | {verdict} | {score} | {gate} | {coverage} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_prd_index(
    prd_dir: Path,
    docsets: list[FeatureDocSet],
    *,
    prd_title: str,
    prd_goal: str,
    affected_project: str,
    generated_at: str,
) -> Path:
    prd_dir.mkdir(parents=True, exist_ok=True)
    path = prd_dir / "index.md"
    path.write_text(
        render_prd_index(
            docsets,
            prd_title=prd_title,
            prd_goal=prd_goal,
            affected_project=affected_project,
            generated_at=generated_at,
        ),
        encoding="utf-8",
    )
    return path
