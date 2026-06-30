# goal-generator v2

**Loop Engineering Skill** — Generates optimal `/goal` prompts for AI coding agent loops.

Compatible with: **Claude Code · Hermes Agent · Codex CLI · Cursor**

---

## What's new in v2.1

- **Goal prompt guaranteed < 4000 chars** (copy-paste budget, newlines counted).
- **Plan-backed goals**: tasks needing real context no longer inline everything.
  The skill calls **`/plan`** to write `docs/goals/<slug>-plan.md`, then emits a
  compact goal that points to that file.
- **Quality score in every response**: the skill reports a `NN/100` rubric score
  for the goal it just produced, plus 2–4 follow-up questions to sharpen it.
- The goal is emitted inside a ` ```goal ` fenced block so it stays
  machine-extractable even with the quality report appended.
- `validate_goal.py` now prints `QUALITY_SCORE: NN/100` and enforces the 4000-char
  hard cap; `generate-goal.sh` extracts the goal from the ` ```goal ` block.

## What's new in v2

- **Product engineering templates**: `linear-ticket`, `poc-branch`, `ux-validation`,
  `perf-regression`, `api-contract`, `ab-test-setup`, `rollout-gate`,
  `incident-repro`, `changelog-release`, `sla-audit`
- Proof mechanisms extended to MCP calls (Linear, GitHub, Slack)
- `validate_goal.py` updated: accepts MCP calls as valid proof commands
- Full workflow for Linear ticket end-to-end (code → proof → comment → status)
- POC branch comparison workflow with structured KPI JSON schema

---

## Installation

```bash
# Claude Code (project-level — goes to git, shared with team)
cp -r goal-generator .claude/skills/

# Claude Code (global)
cp -r goal-generator ~/.claude/skills/

# Hermes Agent (global)
cp -r goal-generator ~/.hermes/skills/
```

---

## Usage

### Interactive
```
/goal-generator linear-ticket ENG-1234
/goal-generator poc-branch "Compare Redis vs in-memory cache on /api/feed"
/goal-generator ux-validation "Login → Dashboard → Settings flow on staging"
```

### Programmatic
The skill response now contains a ` ```goal ` block plus a quality report, so
extract the goal from that block (or use `scripts/generate-goal.sh`, which
extracts + validates and prints the quality report to stderr):
```bash
# Easiest: the helper extracts the goal, validates it, prints the score to stderr
GOAL=$(scripts/generate-goal.sh linear-ticket "ENG-1234")
claude -p "/goal $GOAL"

# Or extract the goal block yourself
GOAL=$(claude -p "/goal-generator linear-ticket ENG-1234" \
  | awk '/^```goal/{f=1;next} /^```/{f=0} f' | sed '/^📄 Plan:/d')
claude -p "/goal $GOAL"
```

### From a Linear webhook
```bash
#!/bin/bash
# Trigger: ticket moved to "In Progress" in Linear
GOAL=$(scripts/generate-goal.sh linear-ticket "$LINEAR_TICKET_ID")
claude --skip-permissions -p "/goal $GOAL"
```

### From a CI merge gate (POC comparison)
```bash
GOAL=$(scripts/generate-goal.sh poc-branch "Redis cache vs in-memory on /api/feed")
claude -p "/goal $GOAL"
```

---

## Output format

Every invocation returns:

1. The goal prompt inside a ` ```goal ` block (under 4000 chars, copy-paste ready).
   - For plan-backed goals, a `📄 Plan: docs/goals/<slug>-plan.md` line points to
     the `/plan`-generated document that holds the full detail.
2. A `## 📊 Goal quality score: NN/100` section with a per-dimension breakdown.
3. A `## 🔧 Follow-up questions to sharpen the goal` section (2–4 questions).

When a task is too detailed for a compact goal, the skill writes the plan to
`docs/goals/<slug>-plan.md` (via `/plan`) and the goal simply says
`Execute the plan in docs/goals/<slug>-plan.md.` — keeping the prompt short.

---

## All task types

### Engineering
| token | Use for |
|---|---|
| `code-refactor` | Restructure without changing external behaviour |
| `migration` | Move code/data/APIs from one form to another |
| `test-stabilization` | Make flaky tests reliably green |
| `data-pipeline` | Build or fix ETL/ELT flows |
| `dependency-bump` | Upgrade deps with passing tests |
| `ci-fix` | Repair a broken CI/CD step |
| `feature-add` | Add a scoped feature with acceptance criteria |
| `security-patch` | Fix CVE or audit finding |
| `docs-sync` | Sync docs to current code state |

### Product engineering
| token | Use for |
|---|---|
| `linear-ticket` | Implement ticket: code → proof → comment → status |
| `poc-branch` | POC in isolated branch + KPI comparison vs main |
| `ux-validation` | Playwright/ProofShot UI flow validation + screenshots |
| `perf-regression` | Detect and fix a performance regression vs baseline |
| `api-contract` | Verify API contract not broken after refactor |
| `ab-test-setup` | Wire feature flag + A/B infrastructure |
| `rollout-gate` | Progressive rollout health checks |
| `incident-repro` | Reproduce production incident in staging + evidence |
| `changelog-release` | Auto-generate changelog, tag, draft GitHub Release |
| `sla-audit` | Audit service against SLA thresholds, open breach tickets |
| `custom` | Free-form — skill derives proof mechanism |

---

## Adding a new template

1. Create `references/templates/my-template.md`
2. Follow this structure:
   ```markdown
   # Template: my-template
   ## Purpose
   [one sentence]
   ## Done when
   [proof command] [expected output]
   ## Standard constraints
   - [constraint 1]
   ## Typical MAX_ATTEMPTS: [n]
   ## Escalate if: [condition]
   ```
3. Add the token to the task type table in `SKILL.md` under the right category
4. That's it — the skill auto-loads templates by name

---

## MCP setup for product templates

```bash
# Linear (required for linear-ticket, sla-audit)
claude mcp add --transport http linear https://mcp.linear.app/mcp
claude -p "/mcp"   # OAuth flow

# GitHub (required for changelog-release, ci-fix)
claude mcp add github npx -y @anthropic-ai/github-mcp-server

# ProofShot (required for ux-validation, linear-ticket with UI)
npm install -g proofshot-cli
```

---

## File structure

```
goal-generator/
├── SKILL.md
├── README.md
├── scripts/
│   ├── validate_goal.py
│   └── generate-goal.sh
└── references/
    └── templates/
        ├── -- engineering --
        ├── code-refactor.md
        ├── migration.md
        ├── test-stabilization.md
        ├── data-pipeline.md
        ├── dependency-bump.md
        ├── ci-fix.md
        ├── feature-add.md
        ├── security-patch.md
        ├── docs-sync.md
        ├── -- product engineering --
        ├── linear-ticket.md     ← NEW
        ├── poc-branch.md        ← NEW
        ├── ux-validation.md     ← NEW
        ├── perf-regression.md   ← NEW
        ├── api-contract.md      ← NEW
        ├── ab-test-setup.md     ← NEW
        ├── rollout-gate.md      ← NEW
        ├── incident-repro.md    ← NEW
        ├── changelog-release.md ← NEW
        ├── sla-audit.md         ← NEW
        └── custom.md
```

## License
MIT
