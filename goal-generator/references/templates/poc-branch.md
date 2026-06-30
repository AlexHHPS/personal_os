# Template: poc-branch

## Purpose
Build a proof-of-concept in an isolated git branch, run it against a defined
flow or use case, compare performance/KPI metrics against the main branch,
and produce a structured comparison report.

## Goal structure

### Done when (ALL must be true)
1. POC branch exists and CI passes on it
2. Benchmark file `poc-results/comparison.json` exists and is valid JSON
3. `jq .verdict poc-results/comparison.json` outputs either "POC_WINS", "MAIN_WINS", or "INCONCLUSIVE"
4. `poc-results/comparison.md` exists with human-readable summary

### Workflow the agent must follow
```
Step 1 — Baseline on main
  git checkout main
  [run_benchmark_command] > poc-results/main-baseline.json

Step 2 — Create POC branch
  git checkout -b poc/[description]-$(date +%Y%m%d)

Step 3 — Implement POC
  [implement changes scoped to poc scope only]

Step 4 — Benchmark on POC branch
  [run_benchmark_command] > poc-results/poc-results.json

Step 5 — Compare
  python3 poc-results/compare.py main-baseline.json poc-results.json > poc-results/comparison.json

Step 6 — Generate report
  python3 poc-results/report.py > poc-results/comparison.md

Step 7 — Push and open draft PR
  git push origin poc/[branch-name]
  gh pr create --draft --title "POC: [description]" --body "$(cat poc-results/comparison.md)"
```

### KPI comparison schema (poc-results/comparison.json)
```json
{
  "scenario": "[description of the flow tested]",
  "timestamp": "[ISO timestamp]",
  "main": {
    "p50_ms": 0, "p95_ms": 0, "p99_ms": 0,
    "rps": 0, "error_rate": 0, "memory_mb": 0
  },
  "poc": {
    "p50_ms": 0, "p95_ms": 0, "p99_ms": 0,
    "rps": 0, "error_rate": 0, "memory_mb": 0
  },
  "delta": {
    "p50_pct": 0, "p95_pct": 0, "rps_pct": 0
  },
  "verdict": "POC_WINS | MAIN_WINS | INCONCLUSIVE",
  "verdict_reason": "string"
}
```

### Verdict rules (derive from delta)
- `POC_WINS`: p95 improves > 10% AND error_rate does not increase
- `MAIN_WINS`: p95 degrades > 5% OR error_rate increases > 0.1%
- `INCONCLUSIVE`: deltas within noise margin (< 5% on all metrics)

### Benchmark tools by stack (fill in at invocation time)
| Stack | Benchmark command |
|---|---|
| HTTP API | `k6 run scripts/benchmark.js --env BASE_URL=[url]` |
| Python function | `hyperfine --warmup 3 "python -c 'from app import fn; fn()'"` |
| DB query | `pgbench -c 10 -T 30 [db_name]` |
| Frontend bundle | `lighthouse [url] --output json --output-path poc-results/lh.json` |
| CLI tool | `hyperfine --warmup 5 "[command]"` |

## Standard constraints
- POC branch must be isolated: branch off main, not off any feature branch
- Do not modify main, staging, or production
- poc-results/ directory must be committed to the branch (not gitignored)
- Do not open a non-draft PR — always draft until human review

## Full goal example (PLAN-BACKED form)
This workflow has a 7-step sequence, so use Form B (SKILL.md Step 4): write the
detail to a `/plan`-generated document and emit a compact goal pointing to it,
keeping the goal prompt under 4000 chars.

First write `docs/goals/poc-branch-redis-cache-plan.md` (the 7-step workflow
above, KPI schema, verdict rules, and benchmark commands). Then emit:
```goal
/goal Execute the plan in docs/goals/poc-branch-redis-cache-plan.md.
Done when: `jq .verdict poc-results/comparison.json` outputs "POC_WINS" or "INCONCLUSIVE" AND `gh pr list --head poc/redis-cache --json state -q .[0].state` outputs "OPEN" AND `cat poc-results/comparison.md | wc -l` outputs > 20
CONSTRAINTS: POC scope only src/cache/ and src/api/feed.ts; do not modify auth, payments, or other services; branch name must start with poc/ — full workflow in the plan
MAX_ATTEMPTS: 15
ESCALATE_IF: Docker stack fails to start after 3 attempts, OR baseline benchmark errors > 5% (infra problem, not code)
```
