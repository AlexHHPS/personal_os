# Template: test-stabilization
## Proof mechanism pattern
`[test_runner] [test_path] --count=3` outputs "N passed" with 0 failures across all 3 runs
## Standard constraints
- Do not modify test logic or assertions — only fixtures, mocks, setup/teardown
- Do not skip or xfail tests without explicit approval
## Typical MAX_ATTEMPTS: 10
## Escalate if: same error message appears 3 consecutive runs unchanged
