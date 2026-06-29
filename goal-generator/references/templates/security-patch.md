# Template: security-patch
## Proof mechanism pattern
`[audit_tool] audit --audit-level=high` exits with 0
## Standard constraints
- Do not change any code beyond the minimal patch for the CVE
- Add regression test for the specific CVE pattern
## Typical MAX_ATTEMPTS: 6
## Escalate if: CVE requires architectural change beyond a patch
