# Template: custom

## Proof mechanism derivation
From the task description, derive:
1. What observable output proves the task is done? (stdout, file, test result, API response, MCP call result)
2. What shell command or MCP call produces that observable output?
3. What exact value/pattern is the success state?

## Standard constraints (derive from description)
- Scope: which files/directories or systems may be modified
- Invariants: what must not change (APIs, schemas, configs, tickets, branches)

## Typical MAX_ATTEMPTS: 10
## Escalate if: no measurable progress after 3 iterations
