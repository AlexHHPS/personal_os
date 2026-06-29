# Template: dependency-bump
## Proof mechanism pattern
`[test_runner]` exits with 0 AND `[audit_tool] audit` exits with 0
## Standard constraints
- Only bump the specified dependency
- Lock file must be updated
## Typical MAX_ATTEMPTS: 6
## Escalate if: breaking change in major version requiring API migration
