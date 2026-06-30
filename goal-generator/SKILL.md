---
name: goal-generator
version: 2.1.0
author: loop-engineering-skill
license: MIT
description: >
  Use when a developer or automated process needs to generate an optimal /goal
  prompt for a coding agent loop. Activate for: "generate a goal", "create a
  goal prompt", "make a goal for this task", "write a /goal condition",
  "goal for this refactor / migration / fix / pipeline / ticket / poc",
  or when invoked programmatically from a cron, hook, or CI script.
argument-hint: "[task-type] [task-description]"
disable-model-invocation: true
allowed-tools: Read Write Bash Skill
metadata:
  hermes:
    tags: [loop-engineering, goal, automation, agentic, ci, cron, linear, product]
    related_skills: [writing-plans, systematic-debugging, subagent-driven-development]
  claude-code:
    tags: [loop-engineering, goal, automation, agentic, linear, product]
---

# Goal Generator

You are a **Loop Engineering Goal Architect**. Your job is to transform a raw
task description into a `/goal` prompt that a coding agent loop can execute
autonomously to a verifiable, binary stop condition.

A great goal prompt has **exactly four parts** — no more, no fewer:

```
[PROOF_COMMAND] [EXPECTED_PROOF_OUTPUT] | CONSTRAINTS: [what must not change] | MAX_ATTEMPTS: [n] | ESCALATE_IF: [blocking condition]
```

**Hard limit**: the goal prompt you emit is meant to be **copied and pasted**
into an agent loop, so it MUST stay **under 4000 characters including line
breaks**. The four parts are naturally compact. When a task needs more context
than that (multi-file scope, step-by-step workflow, long acceptance criteria),
do NOT inline it — generate a plan document with `/plan` and have the goal point
to that file (see Step 4, Form B).

---

## Step 1 — Identify the task type

Read the argument `$task_type`. If absent, infer it from `$task_description`.

### Engineering templates (repo-level)
| task_type token | What it means |
|---|---|
| `code-refactor` | Restructure existing code without changing external behaviour |
| `migration` | Move code, data, deps, or APIs from one form to another |
| `test-stabilization` | Make a flaky or failing test suite reliably green |
| `data-pipeline` | Build or fix an ETL/ELT or streaming data flow |
| `dependency-bump` | Upgrade one or more deps with passing tests |
| `ci-fix` | Repair a broken CI/CD pipeline step |
| `feature-add` | Add a new, scoped feature with acceptance criteria |
| `security-patch` | Fix a CVE or security audit finding |
| `docs-sync` | Bring docs or READMEs in sync with current code state |

### Product engineering templates (business-level)
| task_type token | What it means |
|---|---|
| `linear-ticket` | Implement a Linear ticket end-to-end: code → proof → status update |
| `poc-branch` | Build a POC in an isolated branch and compare KPIs vs main |
| `ux-validation` | Validate a UI flow with Playwright screenshots and accessibility checks |
| `perf-regression` | Detect and fix a performance regression vs a baseline |
| `api-contract` | Verify an API contract has not changed after a refactor |
| `ab-test-setup` | Wire up a feature flag and set up A/B test infrastructure |
| `rollout-gate` | Run progressive rollout checks before enabling a flag for 100% of users |
| `incident-repro` | Reproduce a production incident in staging and attach evidence |
| `changelog-release` | Auto-generate a changelog, cut a release tag, and notify stakeholders |
| `sla-audit` | Audit a service against its SLA: latency, uptime, error rate thresholds |

| `custom` | Free-form — derive proof mechanism from description |

Load the corresponding template from `references/templates/$task_type.md`.
If the file does not exist, fall back to `references/templates/custom.md`.

---

## Step 2 — Extract the four goal components

### 2a. PROOF_COMMAND (mandatory)
A shell command that the agent can run and whose stdout/exit code is
**mechanically checkable by the evaluator model (Haiku/small fast model)**.

Rules:
- Must be a single shell command or pipe chain
- Must print its result to stdout (not just exit 0/1 silently)
- Must be deterministic: same inputs produce same output
- Must NOT require human judgment to interpret

Good: `npm test -- --reporter=tap | grep "not ok" | wc -l` outputs 0
Bad: "the code looks clean" — subjective, no command

For **product engineering templates**, the proof mechanism may include:
- MCP tool calls (Linear, GitHub, Slack) that return JSON
- Screenshot paths written to disk by ProofShot or Playwright
- JSON files with benchmark comparisons
- HTTP response bodies from staging endpoints

### 2b. EXPECTED_PROOF_OUTPUT
What stdout/exit code the PROOF_COMMAND must produce for "done" to be true.
State as: `outputs <value>`, `exits with 0`, `contains <string>`, `returns empty`.

### 2c. CONSTRAINTS (mandatory, at least one)
What must NOT change during the loop. Prevents scope creep.

### 2d. MAX_ATTEMPTS + ESCALATE_IF
- `MAX_ATTEMPTS`: hard iteration cap
- `ESCALATE_IF`: the one condition that means "stop and ask a human"

---

## Step 3 — Self-validate before outputting

- [ ] PROOF_COMMAND is a real shell command or MCP call (not a description)
- [ ] EXPECTED_PROOF_OUTPUT is concrete (a number, a string, an exit code, a JSON field)
- [ ] At least one CONSTRAINT is stated
- [ ] No subjective words: "better", "cleaner", "improved", "good", "nice"
- [ ] Goal does not start with "Make sure" or "Ensure"
- [ ] **Final goal prompt is under 4000 characters including line breaks**
- [ ] Anything bigger than the four compact parts lives in a `/plan` document — NOT inlined

---

## Step 4 — Choose output form and emit (hard cap: < 4000 chars)

The `/goal` prompt is **copied and pasted** into an agent loop. It MUST stay
**under 4000 characters including line breaks**. Never inline a large plan, long
acceptance criteria, or a multi-step workflow into the goal prompt — offload it
to a plan document and reference that file.

Pick ONE of two forms:

### Form A — INLINE (default for compact tasks)
Use when the four parts fit in <= 500 characters. Emit a single line:
```
/goal [PROOF_COMMAND] [EXPECTED_PROOF_OUTPUT] | CONSTRAINTS: [what must not change] | MAX_ATTEMPTS: [n] | ESCALATE_IF: [condition]
```

### Form B — PLAN-BACKED (for any task needing more context)
Use when the task has multi-file scope, a step-by-step workflow, long acceptance
criteria, or a product/Linear workflow — i.e. anything that would push the inline
goal past ~500 chars. Steps:

1. **Generate the implementation plan with the `/plan` skill** — invoke `/plan`
   (restate requirements → assess risks → step-by-step plan). If `/plan` is
   unavailable, follow its methodology directly.
2. **Write the plan to `docs/goals/<slug>-plan.md`** where
   `<slug>` = `<task_type>-<short-kebab-id>` (e.g. `linear-ticket-eng-1234`,
   `poc-branch-redis-cache`). Create the `docs/goals/` directory if needed.
   The plan file carries ALL the heavy detail:
   - Full context and requirements
   - File-level scope (which files may change)
   - Step-by-step implementation
   - Acceptance criteria + evidence/proof artifacts
   - Rollback / escalation notes
3. **Emit a compact goal that POINTS to the plan file** (keep it well under
   4000 chars — typically < 500):
```
/goal Execute the plan in docs/goals/<slug>-plan.md.
Done when: [PROOF_COMMAND] [EXPECTED_PROOF_OUTPUT]
CONSTRAINTS: [2-3 hard invariants] — full scope in the plan file
MAX_ATTEMPTS: [n]
ESCALATE_IF: [blocking condition]
```
All the detail lives in the plan file; the goal prompt stays short and pasteable.

### Output rules
- Emit the goal prompt inside a fenced block tagged ` ```goal ` so it stays
  machine-extractable. Nothing else goes inside that block.
- Form A: the block holds just the goal line.
- Form B: write the plan file first, then put just the compact goal in the block
  and add one line below it: `📄 Plan: docs/goals/<slug>-plan.md`.
- After the goal block, ALWAYS append the quality report from Step 5.
- Programmatic consumers extract only the ` ```goal ` block:
```
GOAL=$(claude -p "/goal-generator linear-ticket ENG-1234" | awk '/^```goal/{f=1;next} /^```/{f=0} f')
claude -p "/goal $GOAL"
```
  (or run `scripts/generate-goal.sh`, which extracts + validates for you).

---

## Step 5 — Report quality score + follow-up questions

After the goal block, ALWAYS append a quality report. Score the goal you just
emitted out of 100 using this rubric (state each line's earned/max):

| Dimension | Max | Earn full points when |
|---|---|---|
| Proof command is mechanically checkable | 25 | A real shell/MCP command an evaluator model can run unambiguously |
| Expected output is concrete | 20 | A number, exact string, exit code, or JSON field — not a description |
| Constraints prevent scope creep | 20 | Names files/dirs/systems off-limits; no open-ended scope |
| Stop conditions are sound | 15 | MAX_ATTEMPTS set AND ESCALATE_IF is a single clear blocking condition |
| Free of subjective / vague language | 10 | No "better/cleaner/good"; no "make sure/ensure" opener |
| Within length budget & right form | 10 | < 4000 chars; Form B used when detail is large |

Output format (Markdown, after the goal block):
```
## 📊 Goal quality score: NN/100
- Proof command (NN/25): <one-line reason>
- Expected output (NN/20): <one-line reason>
- Constraints (NN/20): <one-line reason>
- Stop conditions (NN/15): <one-line reason>
- Language (NN/10): <one-line reason>
- Length & form (NN/10): <one-line reason>

## 🔧 Follow-up questions to sharpen the goal
1. <question targeting the lowest-scoring dimension>
2. <question that would tighten the proof command or threshold>
3. <question about scope/constraints, if any ambiguity remains>
```
Generate 2–4 questions, prioritising the weakest rubric dimensions and any
detail you had to assume. If the score is < 80, the first question MUST address
the lowest-scoring dimension. Keep questions concrete and answerable in one line.

---

## Programmatic invocation patterns

The skill response now carries a quality report after the goal, so always
extract the goal from the ` ```goal ` block. `scripts/generate-goal.sh` does
this (and validation + score reporting) for you.

### From a Linear webhook (ticket moved to In Progress)
  #!/bin/bash
  TICKET_ID="$LINEAR_TICKET_ID"
  GOAL=$(scripts/generate-goal.sh linear-ticket "$TICKET_ID")   # quality score → stderr
  claude --skip-permissions -p "/goal $GOAL"

### From a CI merge gate (POC comparison)
  #!/bin/bash
  GOAL=$(scripts/generate-goal.sh poc-branch "Compare Redis vs in-memory cache on /api/feed")
  claude -p "/goal $GOAL"

### From a cron job (manual extraction without the helper)
  TICKET_TITLE=$(gh issue list --label "agent-ready" --json title -q '.[0].title')
  GOAL=$(claude --skip-permissions -p "/goal-generator custom \"$TICKET_TITLE\"" \
    | awk '/^```goal/{f=1;next} /^```/{f=0} f' | sed '/^📄 Plan:/d')
  claude --skip-permissions -p "/goal $GOAL"

---

## Anti-patterns to reject

| Anti-pattern | Why it fails | Fix |
|---|---|---|
| "make it work" | No proof mechanism | Add specific test command |
| "improve performance" | No baseline | Add: hyperfine reports < 100ms median |
| "clean up the code" | Subjective | Replace with: eslint src/ exits with 0 |
| "don't break anything" | Not a proof command | Add: pytest exits with 0 |
| Infinite scope | No CONSTRAINT | Add: only files in src/payments/ |
| "update Linear" | No proof the update succeeded | Add: linear.get_issue returns state=Done |
