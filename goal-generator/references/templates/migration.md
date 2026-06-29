# Template: migration
## Proof mechanism pattern
`grep -r "[old_pattern]" [scope_path] | wc -l` outputs 0 AND `[test_runner]` exits with 0
## Standard constraints
- Only files in [scope_path] may be modified
- Public function signatures must not change
- No schema migrations unless explicitly stated
## Typical MAX_ATTEMPTS: 15
## Escalate if: >5 unique error types after 5 iterations
