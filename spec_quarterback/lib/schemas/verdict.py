"""``CriticVerdict`` — the structured result of one critic review.

This mirrors the JSON output contract defined in
``specs/template/critic/spec_quality_reviewer_prompt.md`` (the canonical, richer
shape — the ``...checklist.json`` is a thinner reference variant). It is the
successor to the old 5-dimension ``QualityScore``.

Unlike the generator's document schemas, ``CriticVerdict`` is NOT bound as a
constrained ``response_format`` call: it is the deepest schema in the system and
would stress llama.cpp's GBNF compiler after ``$ref`` inlining. The refiner
instead asks the critic for raw JSON (``call_freeform``), extracts it
(``json_extract``), and validates it here. The model therefore mixes in nothing
special; it just needs to be tolerant of the two score shapes the prompt and the
checklist emit, and it owns the weighted-score arithmetic so a model that
miscomputes its own total cannot mislead the stop condition.
"""

from __future__ import annotations

import logging
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

# Dimension weights (sum to 1.0). Code owns the weighting so the refiner's bar is
# computed, not taken from the model. The first 8 are internal-quality dimensions
# (the structural critic); the last 2 are PRD-grounded (the fidelity critic). When
# the fidelity pass is off, only the internal dimensions are scored and the
# weighted score renormalises over the present weights (see ``_recompute``).
CRITIC_WEIGHTS: Final[dict[str, float]] = {
    "clarity": 0.12,
    "coverage": 0.15,
    "edge_cases": 0.15,
    "architecture": 0.13,
    "nfr_measurability": 0.08,
    "task_implementability": 0.08,
    "traceability": 0.04,
    "consistency": 0.05,
    "prd_coverage": 0.12,
    "prd_fidelity": 0.08,
}

_VERDICTS: Final[frozenset[str]] = frozenset({"GO", "REVISE", "STOP"})
_SEVERITIES: Final[frozenset[str]] = frozenset({"CRITICAL", "MAJOR", "MINOR"})
_COVERAGE_STATUSES: Final[frozenset[str]] = frozenset(
    {"COVERED", "PARTIAL", "MISSING", "CONTRADICTED", "INVENTED"}
)
# Coverage statuses that the improve step should act on (add / fix the requirement).
_GAP_STATUSES: Final[frozenset[str]] = frozenset({"MISSING", "CONTRADICTED", "PARTIAL"})

# Which document each failing dimension should send the improve step to.
_DIMENSION_DOCS: Final[dict[str, tuple[str, ...]]] = {
    "clarity": ("requirements",),
    "coverage": ("requirements",),
    "edge_cases": ("requirements",),
    "nfr_measurability": ("requirements",),
    "architecture": ("design",),
    "task_implementability": ("tasks",),
    "traceability": ("requirements", "design", "tasks"),
    "consistency": ("requirements", "design", "tasks"),
    "prd_coverage": ("requirements", "design"),
    "prd_fidelity": ("requirements", "design"),
}
_ALL_DOCS: Final[tuple[str, ...]] = ("requirements", "design", "tasks")


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _str(value: object) -> str:
    """Coerce to string; ``None`` -> ``""``. So a stray null in one field never fails
    validation and discards the whole verdict (the critic emits free-form JSON)."""
    return "" if value is None else str(value)


def _str_list(value: object) -> list[str]:
    """Coerce to a list of strings, dropping nulls; a scalar becomes a 1-item list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [_str(x) for x in value if x is not None]
    return [_str(value)]


def _heal_str_fields(d: dict[str, object], *keys: str) -> None:
    """In-place: coerce each present key to a string (None -> "")."""
    for key in keys:
        if key in d:
            d[key] = _str(d[key])


class BinaryGate(BaseModel):
    model_config = ConfigDict(strict=False)
    passed: bool = False
    blockers_failed: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "passed" in d:
            d["passed"] = bool(d.get("passed"))
        d["blockers_failed"] = _str_list(d.get("blockers_failed"))
        return d


class BannedTerm(BaseModel):
    model_config = ConfigDict(strict=False)
    word: str = ""
    location: str = ""
    required_action: str = ""

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        _heal_str_fields(d, "word", "location", "required_action")
        return d


class DimensionScore(BaseModel):
    model_config = ConfigDict(strict=False, extra="ignore")
    score: float = Field(default=0.0)
    weight: float = 0.0


class Issue(BaseModel):
    model_config = ConfigDict(strict=False)
    id: str = ""
    severity: str = "MINOR"
    dimension: str = ""
    location: str = ""
    description: str = ""
    suggestion: str = ""
    blocks_implementation: bool = False

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        _heal_str_fields(d, "id", "dimension", "location", "description", "suggestion")
        sev = str(d.get("severity") or "").strip().upper()
        d["severity"] = sev if sev in _SEVERITIES else "MINOR"
        return d


class IssueSummary(BaseModel):
    model_config = ConfigDict(strict=False)
    critical_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    banned_word_count: int = 0


class CoverageItem(BaseModel):
    """How one PRD contract item fares in the spec (the fidelity critic's verdict)."""

    model_config = ConfigDict(strict=False, extra="ignore")
    contract_id: str = ""
    status: str = "MISSING"
    statement: str = ""
    prd_ref: str = ""
    evidence: str = ""
    note: str = ""

    @model_validator(mode="before")
    @classmethod
    def _heal(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        _heal_str_fields(d, "contract_id", "statement", "prd_ref", "evidence", "note")
        status = str(d.get("status") or "").strip().upper()
        d["status"] = status if status in _COVERAGE_STATUSES else "PARTIAL"
        return d


class CriticVerdict(BaseModel):
    """One critic review of a feature doc-set."""

    model_config = ConfigDict(strict=False, extra="ignore")

    spec_reviewed: str = ""
    reviewed_at: str = ""
    reviewer_role: str = "Full"
    binary_gate: BinaryGate = Field(default_factory=BinaryGate)
    banned_vocabulary: list[BannedTerm] = Field(default_factory=list)
    scores: dict[str, DimensionScore] = Field(default_factory=dict)
    weighted_score: float = 0.0
    issues: list[Issue] = Field(default_factory=list)
    edge_case_coverage: dict[str, bool | str] = Field(default_factory=dict)
    nfr_coverage: dict[str, bool | str] = Field(default_factory=dict)
    coverage: list[CoverageItem] = Field(default_factory=list)
    issue_summary: IssueSummary = Field(default_factory=IssueSummary)
    fix_priority: list[str] = Field(default_factory=list)
    summary: str = ""
    verdict: str = "REVISE"
    confidence: str = "MEDIUM"
    confidence_reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalise(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        d: dict[str, object] = dict(data)

        # scores: accept either {"clarity": 0.8} (checklist) or
        # {"clarity": {"score": 0.8, "weight": 0.15}} (prompt) shapes.
        raw_scores = d.get("scores")
        if isinstance(raw_scores, dict):
            norm: dict[str, dict[str, float]] = {}
            for key, val in raw_scores.items():
                if isinstance(val, dict):
                    norm[key] = {
                        "score": _as_float(val.get("score")),
                        "weight": _as_float(val.get("weight"), CRITIC_WEIGHTS.get(key, 0.0)),
                    }
                else:
                    norm[key] = {"score": _as_float(val), "weight": CRITIC_WEIGHTS.get(key, 0.0)}
            d["scores"] = norm

        verdict = str(d.get("verdict") or "").strip().upper()
        d["verdict"] = verdict if verdict in _VERDICTS else "REVISE"

        for cov_key in ("edge_case_coverage", "nfr_coverage"):
            raw = d.get(cov_key)
            if isinstance(raw, dict):
                d[cov_key] = {str(k): _coerce_cov(v) for k, v in raw.items()}
        if "coverage" in d and not isinstance(d["coverage"], list):
            d["coverage"] = []
        # Coerce stray nulls so one bad field never discards the whole verdict.
        _heal_str_fields(
            d, "spec_reviewed", "reviewed_at", "reviewer_role", "summary",
            "confidence", "confidence_reason",
        )
        if "fix_priority" in d:
            d["fix_priority"] = _str_list(d.get("fix_priority"))
        return d

    @model_validator(mode="after")
    def _recompute(self) -> CriticVerdict:
        # Authoritative weighted score: code-owned, ignores the model's weights, and
        # renormalised over the dimensions actually scored. A structural-only verdict
        # (fidelity off → no prd_* scores) is judged on its present weights rather
        # than penalised for the absent fidelity dimensions; a merged verdict scores
        # over all ten (weights sum to 1.0).
        present = {dim: weight for dim, weight in CRITIC_WEIGHTS.items() if dim in self.scores}
        wsum = sum(present.values())
        if self.scores and wsum:
            computed = sum(self.dimension_score(dim) * w for dim, w in present.items()) / wsum
            self.weighted_score = round(computed, 4)

        # Counts can't lie: recompute from the issue list + banned vocab.
        self.issue_summary = IssueSummary(
            critical_count=sum(1 for i in self.issues if i.severity == "CRITICAL"),
            major_count=sum(1 for i in self.issues if i.severity == "MAJOR"),
            minor_count=sum(1 for i in self.issues if i.severity == "MINOR"),
            banned_word_count=len(self.banned_vocabulary),
        )
        return self

    # --- derived helpers used by the refiner -------------------------------

    def dimension_score(self, name: str) -> float:
        ds = self.scores.get(name)
        return ds.score if ds is not None else 0.0

    @property
    def passed_gate(self) -> bool:
        return self.binary_gate.passed

    @property
    def is_stop(self) -> bool:
        return self.verdict == "STOP"

    def bar_met(self, bar: float) -> bool:
        """The refiner's termination bar: weighted score at/above ``bar`` AND the binary
        gate passed (no hard blocker left).

        Deliberately NOT gated on a ``GO`` verdict label: the structural critic issues
        ``GO`` rarely by design, so tying termination to it would make the nightly refiner
        loop forever even on an excellent spec. A score-based, gate-checked bar is a
        reachable target the loop can actually converge to.
        """
        return self.weighted_score >= bar and self.binary_gate.passed

    def target_docs(self) -> list[str]:
        """Which docs the improve step should rewrite, from the failing issues.

        Falls back to the single lowest-scoring dimension's doc when there are
        no explicit issues (so a sub-bar verdict with empty issues still drives
        a focused rewrite rather than touching everything).
        """
        docs: set[str] = set()
        for issue in self.issues:
            docs.update(_DIMENSION_DOCS.get(issue.dimension, ()))
        if docs:
            # Preserve a stable order.
            return [d for d in _ALL_DOCS if d in docs]
        if self.scores:
            worst = min(CRITIC_WEIGHTS, key=self.dimension_score)
            return list(_DIMENSION_DOCS.get(worst, _ALL_DOCS))
        return list(_ALL_DOCS)

    def issues_for(self, doc: str) -> list[Issue]:
        """Issues whose failing dimension maps to ``doc`` (requirements/design/tasks)."""
        return [i for i in self.issues if doc in _DIMENSION_DOCS.get(i.dimension, _ALL_DOCS)]

    def coverage_gaps(self) -> list[CoverageItem]:
        """PRD contract items the spec fails to honour — what the improve step must fix."""
        return [c for c in self.coverage if c.status in _GAP_STATUSES]

    def invented_scope(self) -> list[CoverageItem]:
        """Scope the spec added with no PRD basis — what the improve step must remove."""
        return [c for c in self.coverage if c.status == "INVENTED"]

    def coverage_summary(self) -> str:
        """One-line tally of the PRD coverage map (empty string when no coverage)."""
        if not self.coverage:
            return ""
        by: dict[str, int] = {}
        for c in self.coverage:
            by[c.status] = by.get(c.status, 0) + 1
        covered = by.get("COVERED", 0)
        order = ("COVERED", "PARTIAL", "MISSING", "CONTRADICTED", "INVENTED")
        parts = [f"{by[s]} {s.lower()}" for s in order if by.get(s)]
        return f"{covered}/{len(self.coverage)} covered · " + " · ".join(parts)


def _coerce_cov(value: object) -> bool | str:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"n/a", "na", "not applicable"}:
        return "N/A"
    return text in {"true", "yes", "1", "covered", "present"}
