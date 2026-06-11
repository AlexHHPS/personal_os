"""Runtime loader for the SDD templates (skeleton + critic) — live config.

The skeleton documents and the critic reviewer prompt live as editable markdown
under ``<workdir>/specs/template/`` so the operator can tune the generated
structure and the quality rubric WITHOUT a code change. This module is the only
place that touches those files; the generator and refiner depend on it, never on
paths.

Resolution is per file: each template is read from the live
``<workdir>/specs/template/<rel>`` if present and non-empty, otherwise from a
packaged fallback copy shipped inside the skill (``lib/templates_data/``). A
template that is missing in both places is a loud error — the flow must never
run with, say, no critic prompt.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, Final

_PKG: Final[str] = "spec_quarterback.lib"
_DATA_DIR: Final[str] = "templates_data"

# Relative paths under specs/template/ (and under the packaged fallback).
REL_CONSTITUTION: Final[str] = "skeleton/constitution.md"
REL_REQUIREMENTS: Final[str] = "skeleton/requirements.md"
REL_DESIGN: Final[str] = "skeleton/design.md"
REL_TASKS: Final[str] = "skeleton/tasks.md"
REL_CRITIC_PROMPT: Final[str] = "critic/spec_quality_reviewer_prompt.md"
REL_FIDELITY_PROMPT: Final[str] = "critic/prd_fidelity_prompt.md"
REL_CRITIC_CHECKLIST: Final[str] = "critic/spec_quality_checklist.json"


class TemplateMissingError(RuntimeError):
    """Raised when a required template is absent from both live and packaged."""


def _read_packaged(rel: str) -> str | None:
    resource = files(_PKG).joinpath(_DATA_DIR)
    for part in rel.split("/"):
        resource = resource.joinpath(part)
    try:
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        return None


def _read_template(rel: str, template_root: Path | None) -> str:
    if template_root is not None:
        live = template_root / rel
        if live.is_file():
            text = live.read_text(encoding="utf-8")
            if text.strip():
                return text
    packaged = _read_packaged(rel)
    if packaged is not None and packaged.strip():
        return packaged
    raise TemplateMissingError(
        f"template {rel!r} not found in live ({template_root}) or packaged fallback"
    )


def _between(text: str, start_substring: str, end_substring: str) -> str:
    """Return the text from the line containing ``start`` up to (not including)
    the next line containing ``end``. Empty string if ``start`` is absent."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if start_substring in ln), None)
    if start is None:
        return ""
    end = next(
        (j for j in range(start + 1, len(lines)) if end_substring in lines[j]), len(lines)
    )
    return "\n".join(lines[start:end]).strip()


def _section(text: str, heading_substring: str) -> str:
    """Return the markdown block whose heading contains ``heading_substring``.

    Matches the first ``#..###### ... <substring> ...`` line (case-insensitive)
    and returns everything up to the next heading of the same or higher level.
    Returns ``""`` when no such heading exists.
    """
    lines = text.splitlines()
    start = None
    start_level = 0
    needle = heading_substring.lower()
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m and needle in m.group(2).lower():
            start = i
            start_level = len(m.group(1))
            break
    if start is None:
        return ""
    collected = [lines[start]]
    for line in lines[start + 1 :]:
        m = re.match(r"^(#{1,6})\s+", line)
        if m and len(m.group(1)) <= start_level:
            break
        collected.append(line)
    return "\n".join(collected).strip()


@dataclass(frozen=True)
class SpecTemplates:
    """The loaded SDD templates. Construct via :func:`load_templates`."""

    constitution_skeleton: str
    requirements_skeleton: str
    design_skeleton: str
    tasks_skeleton: str
    critic_prompt: str
    fidelity_prompt: str
    checklist_schema: dict[str, Any]

    def section(self, doc: str, heading_substring: str) -> str:
        """Pull one section out of a skeleton doc by heading substring."""
        text = {
            "constitution": self.constitution_skeleton,
            "requirements": self.requirements_skeleton,
            "design": self.design_skeleton,
            "tasks": self.tasks_skeleton,
        }.get(doc, "")
        return _section(text, heading_substring)

    def banned_vocabulary(self) -> str:
        """The critic's banned-words list, sliced from the critic prompt.

        Fed into the generation prompts so the generator avoids vocabulary the
        critic flags as MAJOR issues (keeping the rubric the single source of
        truth). Returns ``""`` if the section can't be located.
        """
        return _between(self.critic_prompt, "BANNED WORDS", "PHASE 3")


@lru_cache(maxsize=8)
def load_templates(workdir: Path | None = None) -> SpecTemplates:
    """Load the SDD templates, preferring live files under ``workdir``.

    Args:
        workdir: the skill's workdir (e.g. ``~/Brein``); the loader looks under
            ``<workdir>/specs/template/``. ``None`` (tests / no workdir) uses the
            packaged fallback only.
    """
    template_root = (workdir / "specs" / "template") if workdir is not None else None
    checklist_raw = _read_template(REL_CRITIC_CHECKLIST, template_root)
    try:
        checklist: dict[str, Any] = json.loads(checklist_raw)
    except json.JSONDecodeError:
        checklist = {}
    return SpecTemplates(
        constitution_skeleton=_read_template(REL_CONSTITUTION, template_root),
        requirements_skeleton=_read_template(REL_REQUIREMENTS, template_root),
        design_skeleton=_read_template(REL_DESIGN, template_root),
        tasks_skeleton=_read_template(REL_TASKS, template_root),
        critic_prompt=_read_template(REL_CRITIC_PROMPT, template_root),
        fidelity_prompt=_read_template(REL_FIDELITY_PROMPT, template_root),
        checklist_schema=checklist,
    )


def clear_cache() -> None:
    """Clear the template cache (tests that edit live templates call this)."""
    load_templates.cache_clear()
