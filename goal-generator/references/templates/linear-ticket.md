# Template: linear-ticket

## Purpose
Implement a Linear ticket end-to-end: read requirements, implement, run tests,
capture visual or textual proof of evidence, post it as a Linear comment,
and move the ticket to the correct status.

## Prerequisites (MCPs required)
- Linear MCP: `claude mcp add --transport http linear https://mcp.linear.app/mcp`
- ProofShot (optional, for UI tickets): `npm install -g proofshot-cli`
- GitHub MCP (optional): for auto-linking PRs

## Goal structure

### Done when (ALL must be true)
1. `linear.get_issue($TICKET_ID).state.name` equals `[target_state]`
   (typical values: "In Review", "Done", "Merged")
2. `linear.get_issue($TICKET_ID).comments` contains a comment with
   `proof-of-work:` prefix posted by the agent
3. For code tickets: `[test_runner]` exits with 0

### Proof of evidence strategy by ticket type

| Ticket type | Proof command | Proof artifact |
|---|---|---|
| Bug fix | `[test_runner] [specific_test]` exits with 0 | Test output pasted as comment |
| UI feature | `proofshot run [url] [flow_description]` writes `proofshot-artifacts/SUMMARY.md` | SUMMARY.md content + screenshot path |
| API feature | `curl -s [endpoint] | jq .[proof_field]` outputs expected value | Response JSON pasted as comment |
| Refactor | `[test_runner]` exits with 0 AND `[linter]` exits with 0 | Test output summary |
| Performance | `hyperfine [command]` outputs median < [threshold]ms | hyperfine table pasted as comment |

### Comment format to post on Linear
```
proof-of-work: [ticket-id]
Status: DONE
Timestamp: [ISO timestamp]
Evidence:
[paste proof output here — test results, curl response, screenshot path, etc.]
Branch: [branch-name]
Commit: [git rev-parse HEAD]
```

## Standard constraints
- Do not modify tickets other than $TICKET_ID
- Do not merge to main — only push to feature branch and open PR
- Do not mark Done if any test fails — set to "In Review" instead
- Linear state transitions must follow team workflow (e.g., In Progress → In Review → Done)

## Full goal example (PLAN-BACKED form)
This workflow is multi-step, so use Form B (SKILL.md Step 4): write the detail
to a `/plan`-generated document and emit a compact goal that points to it. This
keeps the goal prompt under 4000 chars.

First write `docs/goals/linear-ticket-$TICKET_ID-plan.md` (full context, file
scope, step-by-step implementation, the proof-of-work comment format above, and
evidence artifacts). Then emit:
```goal
/goal Execute the plan in docs/goals/linear-ticket-$TICKET_ID-plan.md.
Done when: `linear.get_issue($TICKET_ID) | jq .state.name` outputs "In Review" AND `linear.get_issue($TICKET_ID) | jq .comments[].body | grep "proof-of-work"` is non-empty AND `[test_runner]` exits with 0
CONSTRAINTS: do not modify tickets other than $TICKET_ID; do not merge to main; proof comment must include commit SHA + branch — full file scope in the plan
MAX_ATTEMPTS: 12
ESCALATE_IF: requirements ambiguous after reading description + comments, OR test runner fails with >3 distinct error types after 6 iterations
```

## MCP setup reminder
```bash
# Add once per machine / project
claude mcp add --transport http linear https://mcp.linear.app/mcp
# Then authenticate:
claude -p "/mcp"
```
