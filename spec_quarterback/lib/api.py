"""Top-level entry point for the spec_quarterback generator (SDD flow).

Hermes invokes :func:`run_from_prd_file` with a path to a markdown PRD. The flow:

1. read the PRD, resolve its target project (front-matter ``project:`` or an
   explicit override — may be absent for pre-project work) and a stable
   ``prd_slug``;
2. resolve the PRD spec dir: ``<repo_path>/specs/<prd_slug>/`` for a project, or
   ``<root_dir>/specs/<prd_slug>/`` when project-less; the project-level
   constitution lives one level up at ``<specs_root>/constitution.md``;
3. run the two-phase generator (constitution-once -> decompose -> per-feature
   expand) and write each feature's SDD document set as markdown.

The separate Hermes refinement loop (:mod:`.refiner`) then iterates over the
written documents with the critic to raise their quality. No Linear, no publish,
no network side effect beyond the OmniRoute calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import frontmatter
from openai import AsyncOpenAI

from spec_quarterback.lib.generator import (
    DEFAULT_CONCURRENCY,
    DEFAULT_OMNIROUTE_MODEL,
    GenerateResult,
    run_generator,
)
from spec_quarterback.lib.text import slugify

_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)

# Front-matter label for specs generated without a target project (the
# pre-project case). A display label, never a registry key.
UNSCOPED_LABEL = "(unscoped)"


class SpecQuarterbackError(Exception):
    """Raised on operator-facing configuration / input errors."""


@dataclass(frozen=True)
class PrdInput:
    """A parsed PRD ready for generation (``affected_project`` may be None)."""

    prd_text: str
    affected_project: str | None
    prd_slug: str
    prd_title: str
    source_prd: str


def _first_h1(text: str) -> str | None:
    match = _H1_RE.search(text)
    return match.group(1).strip() if match else None


def load_prd(prd_path: str | Path, *, project_override: str | None = None) -> PrdInput:
    """Read a markdown PRD and resolve its (optional) project + slug."""
    path = Path(prd_path).expanduser()
    if not path.is_file():
        raise SpecQuarterbackError(f"PRD file not found: {path}")

    post = frontmatter.loads(path.read_text(encoding="utf-8"))
    meta = dict(post.metadata)
    body = str(post.content)

    project = project_override or meta.get("project")
    title = str(meta.get("title") or _first_h1(body) or path.stem)
    slug = str(meta.get("slug") or slugify(title))
    return PrdInput(
        prd_text=body,
        affected_project=str(project) if project else None,
        prd_slug=slug,
        prd_title=title,
        source_prd=str(path),
    )


def resolve_spec_dir(
    *,
    affected_project: str | None,
    prd_slug: str,
    registry_path: Path | None = None,
    root_dir: Path | None = None,
) -> Path:
    """Resolve the PRD's spec dir: ``<root|repo>/specs/<prd_slug>/``.

    Project-less PRDs write under ``root_dir``; project PRDs write under the
    project's ``repo_path`` (from ``projects.yaml``). The project-level
    constitution lives at the parent (``<specs_root>/constitution.md``).
    """
    if affected_project is None:
        if root_dir is None:
            raise SpecQuarterbackError(
                "project-less PRD but no root_dir given; nowhere to store specs"
            )
        return root_dir.expanduser() / "specs" / prd_slug

    if registry_path is None:
        raise SpecQuarterbackError(
            f"project {affected_project!r} given but no registry_path to resolve it"
        )
    # Imported lazily so project-less generation (the Railway path) never imports
    # ``personal_os.domains`` — keeps the package self-contained for vendoring. In
    # a standalone/vendored deployment (no personal_os on the box) this path is
    # unsupported: surface a clear operator error instead of a raw ImportError.
    try:
        from personal_os.domains.projects.store import RegistryStore
    except ImportError as exc:
        raise SpecQuarterbackError(
            f"project-scoped specs for {affected_project!r} need the personal_os "
            "registry, unavailable in this deployment; generate project-less with root_dir"
        ) from exc

    registry = RegistryStore(registry_path).load()
    project = registry.find(affected_project)
    if project is None:
        raise SpecQuarterbackError(f"unknown project {affected_project!r}; not in {registry_path}")
    if project.repo_path is None:
        raise SpecQuarterbackError(
            f"project {affected_project!r} has no repo_path; cannot store specs per-project"
        )
    return project.repo_path / "specs" / prd_slug


async def generate_specs(
    *,
    prd_text: str,
    affected_project: str,
    prd_slug: str,
    prd_title: str,
    source_prd: str,
    prd_dir: Path,
    specs_root: Path,
    em_context: str = "",
    omniroute_endpoint: str,
    omniroute_api_key: str | None = None,
    omniroute_model: str = DEFAULT_OMNIROUTE_MODEL,
    workdir: Path | None = None,
    max_features: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    generated_at: datetime | None = None,
) -> GenerateResult:
    """Run the generator against a fully-resolved destination and persist."""
    client = AsyncOpenAI(base_url=omniroute_endpoint, api_key=omniroute_api_key or "not-needed")
    try:
        return await run_generator(
            prd_text=prd_text,
            prd_slug=prd_slug,
            prd_title=prd_title,
            affected_project=affected_project,
            source_prd=source_prd,
            specs_root=specs_root,
            prd_dir=prd_dir,
            client=client,
            model=omniroute_model,
            em_context=em_context,
            workdir=workdir,
            max_features=max_features,
            concurrency=concurrency,
            generated_at=generated_at,
        )
    finally:
        await client.close()


async def run_from_prd_file(
    *,
    prd_path: str | Path,
    registry_path: Path | None = None,
    omniroute_endpoint: str,
    project_override: str | None = None,
    root_dir: Path | None = None,
    workdir: Path | None = None,
    omniroute_api_key: str | None = None,
    omniroute_model: str = DEFAULT_OMNIROUTE_MODEL,
    em_context: str = "",
    max_features: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    generated_at: datetime | None = None,
) -> GenerateResult:
    """Hermes entry point: PRD markdown file -> per-feature SDD document sets.

    ``workdir`` is the Personal OS workspace (``~/Brein``) and is where the live
    ``specs/template/`` skeleton + critic are loaded from; it defaults to
    ``root_dir``. Output goes to ``<root_dir|repo_path>/specs/<slug>/``.
    """
    prd = load_prd(prd_path, project_override=project_override)
    prd_dir = resolve_spec_dir(
        affected_project=prd.affected_project,
        prd_slug=prd.prd_slug,
        registry_path=registry_path,
        root_dir=root_dir,
    )
    return await generate_specs(
        prd_text=prd.prd_text,
        affected_project=prd.affected_project or UNSCOPED_LABEL,
        prd_slug=prd.prd_slug,
        prd_title=prd.prd_title,
        source_prd=prd.source_prd,
        prd_dir=prd_dir,
        specs_root=prd_dir.parent,
        em_context=em_context,
        omniroute_endpoint=omniroute_endpoint,
        omniroute_api_key=omniroute_api_key,
        omniroute_model=omniroute_model,
        workdir=workdir or root_dir,
        max_features=max_features,
        concurrency=concurrency,
        generated_at=generated_at,
    )
