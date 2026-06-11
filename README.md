# spec-quarterback

Decompose a PRD into per-feature SDD (spec-driven development) doc sets, then
raise their quality with a critic-driven refinement loop.

Two stages, one engine:

- **Generate** — reads a PRD markdown file, decomposes it into features, and
  expands each feature into a full doc set (`spec.md`, `plan.md`, `tasks.md`,
  `design.md`, `constitution.md`, …) under `<root-dir>/specs/<slug>/`.
- **Refine** — a critic reviews an existing doc set against a quality rubric
  and an improver rewrites the weakest documents, iterating until the verdict
  clears or the budget runs out.

## Install

```bash
pip install .
```

Requires Python ≥ 3.11. Dependencies: `openai` (OpenAI-compatible client),
`pydantic`, `python-frontmatter`.

## Usage

```bash
spec-quarterback generate --prd path/to/prd.md --root-dir path/to/repo
spec-quarterback refine --prd-dir path/to/repo/specs/<slug>
spec-quarterback refine --all --root-dir path/to/repo   # refine every doc set
```

Also runnable as `python -m spec_quarterback`.

### LLM configuration

The endpoint resolves from flags → environment → defaults:

| Variable | Meaning | Default |
|---|---|---|
| `SPEC_LLM_BASE_URL` | OpenAI-compatible base URL | `https://openrouter.ai/api/v1` |
| `SPEC_LLM_API_KEY` | API key (falls back to `OPENROUTER_API_KEY`) | — |
| `SPEC_LLM_MODEL` | Model id | — |

Point `SPEC_LLM_BASE_URL` at any OpenAI-compatible gateway (a local router,
vLLM, Ollama's compat endpoint, …) to run against other backends.

### Templates

The doc-set skeleton and the critic rubric are bundled in
`spec_quarterback/lib/templates_data/` and resolved via `importlib.resources`,
so the installed package works standalone. If a live `specs/template/` tree
exists under `--root-dir`, it takes precedence — edit those files to customize
the generated documents.

## Hermes agent integration

`hermes/` contains the two skill playbooks for running this as
[Hermes](https://github.com/your-org/hermes) agent skills:

- `SKILL.spec_quarterback.md` — the generator playbook
- `SKILL.spec_refiner.md` — the refinement / nightly-loop playbook

Install the package into the agent's venv, drop each playbook into the
profile's `skills/<name>/SKILL.md`, and set the `SPEC_LLM_*` variables.
