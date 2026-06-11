---
name: spec_quarterback
description: Decompose a markdown PRD into per-feature Spec-Driven-Development document sets (constitution + requirements + design + tasks).
version: 3.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [spec, decomposition, sdd, markdown]
    category: spec
---

# Spec Quarterback (SDD generator) — Railway

Turn a markdown PRD into a set of **features** and expand each into its own
Spec-Driven-Development document set (`requirements.md`, `design.md`,
`tasks.md`) under `<root>/specs/<prd-slug>/<feature>/`. A project-level
`constitution.md` is generated once and reused. The companion `spec_refiner`
skill runs the critic over the output to raise quality.

No Linear, no external publish — the only side effects are the model calls and
writing markdown files.

## Invocation (deterministic CLI)

The engine ships as the `spec-quarterback` console script (installed in the
Hermes venv). Run it directly — do NOT hand-write Python:

```bash
spec-quarterback generate --prd <path-to-prd.md> --root-dir <workspace>
```

`<workspace>` is where specs are written (`<workspace>/specs/<prd-slug>/`). Use
the owned product-brain repo checkout when generating for a product, or a
scratch dir on the volume otherwise.

## LLM configuration (environment)

The CLI resolves its model from the environment (flags override):

- `SPEC_LLM_BASE_URL` — OpenAI-compatible base URL (default OpenRouter).
- `SPEC_LLM_API_KEY` — falls back to `OPENROUTER_API_KEY`.
- `SPEC_LLM_MODEL` — **required**; a strong reasoning model (Sonnet-class).

## Templates are packaged config

The skeletons + critic rubric ship inside the package (`lib/templates_data/`).
On Railway there is no live `specs/template/` tree, so the packaged copies are
used automatically. Retuning the rubric is a code change + redeploy (by design —
a rubric change is a method change).

## Resilience

Every step runs through an LLM; format drift is expected. Schemas are lenient
(optional fields + self-healing) and responses parse tolerantly with one retry,
degrading to a placeholder doc rather than crashing. A thin doc is graded down
by `spec_refiner`, not rejected here.

## Idempotency & locking

- Re-running on an unchanged PRD skips unchanged docs (per-file content hash).
- A `locked: true` document is never overwritten (per file).
- The constitution is never regenerated once present.

## After a successful run

Enqueue refinement of the same PRD:

```bash
spec-quarterback refine --prd-dir <root>/specs/<prd-slug>
```

## Output (stdout summary)

```yaml
prd: prd-ev-phev-comparison-web-app
project: (unscoped)
status: ok
duration_seconds: 95
constitution: created
data_model: created
features: 5
created: 15
updated: 0
unchanged: 0
locked: 0
llm_calls: 17
prd_dir: <workspace>/specs/prd-ev-phev-comparison-web-app
```

## Notes

- Cost scales with features: ~`1 (constitution) + 1 (decompose) + 3 × features`
  calls. Use `--max-features` to bound a run.
