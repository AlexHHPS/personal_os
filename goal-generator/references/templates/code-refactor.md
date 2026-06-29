# Template: code-refactor
## Proof mechanism pattern
`[linter] [target_path]` exits with 0 AND `[test_runner] [test_path]` exits with 0
## Standard constraints
- Do not change public API surface (exported functions, types, HTTP routes)
- No new dependencies
## Typical MAX_ATTEMPTS: 8
## Escalate if: circular dependency introduced or >3 test regressions
