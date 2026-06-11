"""Deterministic command-line entry point for the spec_quarterback skill.

The skill has historically been driven by a Hermes agent hand-writing an
``asyncio.run(...)`` snippet against :mod:`.lib.api` / :mod:`.lib.refiner`. That
is fragile on a long multi-feature loop. This CLI turns invocation into a single
runnable command so a hosted agent (or a cron) only has to run, not author,
Python:

    spec-quarterback generate --prd PATH --root-dir DIR
    spec-quarterback refine --prd-dir DIR
    spec-quarterback refine --all --root-dir DIR        # nightly grind

The LLM endpoint is resolved from flags → environment → defaults so the same
binary works against the local OmniRoute (``SPEC_LLM_BASE_URL=http://localhost:20128/v1``)
and a hosted provider (defaults to OpenRouter). It is intentionally side-effect
free beyond the model calls and writing markdown under ``<root-dir>/specs/``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from spec_quarterback.lib.api import (
    SpecQuarterbackError,
    run_from_prd_file,
)
from spec_quarterback.lib.generator import (
    DEFAULT_CONCURRENCY,
    GenerateResult,
)
from spec_quarterback.lib.refiner import (
    DEFAULT_MAX_ITERS,
    DEFAULT_QUALITY_BAR,
    RefineRunResult,
    refine_specs,
)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


class CliError(SpecQuarterbackError):
    """Operator-facing CLI usage / configuration error."""


def _resolve_llm(args: argparse.Namespace) -> tuple[str, str | None, str]:
    """Resolve (base_url, api_key, model) from flags → env → defaults."""
    base_url = args.base_url or os.environ.get("SPEC_LLM_BASE_URL") or DEFAULT_BASE_URL
    api_key = (
        args.api_key
        or os.environ.get("SPEC_LLM_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
    )
    model = args.model or os.environ.get("SPEC_LLM_MODEL")
    if not model:
        raise CliError("no model: pass --model or set SPEC_LLM_MODEL / OPENROUTER model id")
    return base_url, api_key, model


def _opt_path(value: str | None) -> Path | None:
    return Path(value).expanduser() if value else None


def _discover_prd_dirs(root: Path) -> list[Path]:
    """Every PRD spec dir under ``<root>/specs/`` (refine --all).

    A PRD dir is a child of ``specs/`` that holds an ``index.md`` or at least one
    ``feature-*`` folder; the ``template`` tree and loose files are skipped.
    """
    specs = root / "specs"
    if not specs.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(specs.iterdir()):
        if not child.is_dir() or child.name == "template":
            continue
        if (child / "index.md").is_file() or any(child.glob("feature-*")):
            found.append(child)
    return found


def _summarize_generate(result: GenerateResult) -> str:
    report = result.write_report
    return "\n".join(
        [
            f"prd: {result.prd_slug}",
            f"project: {result.affected_project}",
            "status: ok",
            f"duration_seconds: {result.duration_seconds:.0f}",
            f"constitution: {result.constitution_action}",
            f"data_model: {result.data_model_action}",
            f"features: {len(result.feature_plan.features)}",
            f"created: {len(report.created)}",
            f"updated: {len(report.updated)}",
            f"unchanged: {len(report.unchanged)}",
            f"locked: {len(report.locked)}",
            f"llm_calls: {result.llm_calls}",
            f"prd_dir: {result.prd_dir}",
        ]
    )


def _summarize_refine(result: RefineRunResult) -> str:
    lines = [
        f"prd_dir: {result.prd_dir}",
        "status: ok",
        f"duration_seconds: {result.duration_seconds:.0f}",
        f"refined: {len(result.results)}",
        f"skipped_locked: {len(result.skipped_locked)}",
        "verdicts:",
    ]
    for feature_id, res in result.results.items():
        verdict = res.verdict
        gate = "pass" if verdict.binary_gate.passed else "fail"
        lines.append(
            f"  {feature_id}: {{ verdict: {verdict.verdict}, "
            f"score: {verdict.weighted_score:.2f}, gate: {gate}, "
            f"iterations: {res.iterations} }}"
        )
    return "\n".join(lines)


def _run_generate(args: argparse.Namespace) -> int:
    base_url, api_key, model = _resolve_llm(args)
    result = asyncio.run(
        run_from_prd_file(
            prd_path=args.prd,
            omniroute_endpoint=base_url,
            omniroute_api_key=api_key,
            omniroute_model=model,
            root_dir=_opt_path(args.root_dir),
            registry_path=_opt_path(args.registry),
            project_override=args.project,
            workdir=_opt_path(args.workdir),
            max_features=args.max_features,
            concurrency=args.concurrency,
        )
    )
    print(_summarize_generate(result))
    return 0


def _run_refine(args: argparse.Namespace) -> int:
    base_url, api_key, model = _resolve_llm(args)
    if args.all:
        if not args.root_dir:
            raise CliError("refine --all requires --root-dir")
        prd_dirs = _discover_prd_dirs(Path(args.root_dir).expanduser())
        if not prd_dirs:
            print(f"status: ok\nrefined: 0\nnote: no PRD spec dirs under {args.root_dir}/specs")
            return 0
    else:
        if not args.prd_dir:
            raise CliError("refine requires --prd-dir (or --all --root-dir)")
        prd_dirs = [Path(args.prd_dir).expanduser()]

    workdir = _opt_path(args.workdir)
    for prd_dir in prd_dirs:
        result = asyncio.run(
            refine_specs(
                prd_dir=prd_dir,
                omniroute_endpoint=base_url,
                omniroute_api_key=api_key,
                omniroute_model=model,
                workdir=workdir,
                max_iters=args.max_iters,
                quality_bar=args.quality_bar,
                concurrency=args.concurrency,
                fidelity=not args.no_fidelity,
            )
        )
        print(_summarize_refine(result))
        print("---")
    return 0


def _add_llm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", help="model id (or env SPEC_LLM_MODEL)")
    parser.add_argument("--base-url", help="OpenAI-compatible base url (env SPEC_LLM_BASE_URL)")
    parser.add_argument("--api-key", help="API key (env SPEC_LLM_API_KEY / OPENROUTER_API_KEY)")
    parser.add_argument("--workdir", help="dir with live specs/template/ (else packaged)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spec-quarterback",
        description="PRD -> per-feature SDD specs, then refine them against a critic.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="PRD markdown -> per-feature SDD document sets")
    gen.add_argument("--prd", required=True, help="path to the markdown PRD")
    gen.add_argument("--root-dir", help="root for project-less specs (<root>/specs/<slug>/)")
    gen.add_argument("--project", help="project key override (requires --registry)")
    gen.add_argument("--registry", help="projects.yaml path (only for project-scoped PRDs)")
    gen.add_argument("--max-features", type=int, default=None, help="bound features generated")
    gen.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    _add_llm_args(gen)
    gen.set_defaults(func=_run_generate)

    ref = sub.add_parser("refine", help="critic-driven improvement loop over generated specs")
    ref.add_argument("--prd-dir", help="a single resolved PRD spec dir")
    ref.add_argument("--all", action="store_true", help="refine all PRD dirs under <root>/specs")
    ref.add_argument("--root-dir", help="root scanned by --all")
    ref.add_argument("--max-iters", type=int, default=DEFAULT_MAX_ITERS)
    ref.add_argument("--quality-bar", type=float, default=DEFAULT_QUALITY_BAR)
    ref.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    ref.add_argument("--no-fidelity", action="store_true", help="structural critic only")
    _add_llm_args(ref)
    ref.set_defaults(func=_run_refine)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except SpecQuarterbackError as exc:
        print(f"status: failed\nerror: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - module-exec entry
    raise SystemExit(main())
