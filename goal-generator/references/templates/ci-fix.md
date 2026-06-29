# Template: ci-fix
## Proof mechanism pattern
`gh run list --limit 1 --json conclusion -q '.[0].conclusion'` outputs "success"
## Standard constraints
- Do not change pipeline logic — only fix the broken step
- No secrets in pipeline files; pipeline must remain idempotent
## Typical MAX_ATTEMPTS: 8
## Escalate if: root cause is in a third-party action with no available fix
