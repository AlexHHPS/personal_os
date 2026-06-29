# Template: data-pipeline
## Proof mechanism pattern
`python [pipeline_script] --dry-run 2>&1 | tail -1` outputs "SUCCESS: N records processed"
## Standard constraints
- Do not modify source or destination schema without approval
- Idempotency: running twice must produce the same output
- No hardcoded credentials — use env vars
## Typical MAX_ATTEMPTS: 12
## Escalate if: data loss detected (output record count < input record count)
