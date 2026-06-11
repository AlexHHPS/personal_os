---
name: spec_refiner
description: Score each feature's SDD document set with the critic and iteratively improve it until it clears the bar.
version: 2.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [spec, refinement, critic, quality]
    category: spec
---

# Spec Refiner (critic-driven refinement loop) — Railway

Raise the quality of the document sets produced by `spec_quarterback`. For each
feature folder:

```
review (structural critic + PRD-fidelity critic -> merged verdict)
  -> [improve targeted docs -> review] x N
```

stopping on **GO** over the bar with the gate passed, on **STOP** (a structural
blocker), on convergence, or at `max_iters`. The best-scoring version seen is
always kept. This is the **nightly self-improvement** half — it is designed to
keep raising each spec across runs, not one-shot.

## Invocation (deterministic CLI)

```bash
# one PRD
spec-quarterback refine --prd-dir <root>/specs/<prd-slug>

# nightly grind over every PRD under <root>/specs/
spec-quarterback refine --all --root-dir <root>
```

Options: `--max-iters` (default 3), `--quality-bar` (default 0.9),
`--concurrency` (default 3), `--no-fidelity` (structural critic only).

## LLM configuration (environment)

Same as `spec_quarterback`: `SPEC_LLM_BASE_URL`, `SPEC_LLM_API_KEY`
(`OPENROUTER_API_KEY` fallback), `SPEC_LLM_MODEL` (Sonnet-class).

## Two critics, merged

Each review runs a **structural** critic (internal quality) and a
**PRD-fidelity** critic (compares the spec to a per-feature `contract.md`,
extracted once) concurrently, then merges them: a fidelity gap on a MUST item
fails the gate, so a drifted spec cannot reach GO. The merged verdict scores 10
weighted dimensions; the weighted-score arithmetic is renormalised over the
dimensions actually scored.

## Cost is bounded

STOP short-circuit, convergence detection, and targeted improves keep it
bounded. `locked` documents are never rewritten; the loop never keeps a
regression. Cost ≈ `max_iters × features × (improves + 1)` + one initial review
per feature — bound `--max-iters`/`--max-features` for the nightly cron.

## Output (stdout summary)

```yaml
prd_dir: <root>/specs/prd-ev-phev-comparison-web-app
status: ok
duration_seconds: 70
refined: 2
skipped_locked: 0
verdicts:
  feature-01: { verdict: REVISE, score: 0.76, gate: pass, iterations: 1 }
  feature-02: { verdict: STOP,   score: 0.00, gate: fail, iterations: 0 }
```
