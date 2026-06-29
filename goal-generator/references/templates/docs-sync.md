# Template: docs-sync
## Proof mechanism pattern
`grep -rn "TODO\|FIXME\|OUTDATED" [docs_path] | wc -l` outputs 0
## Standard constraints
- Do not change code to match docs — only docs to match code
- Preserve existing structure and headings
## Typical MAX_ATTEMPTS: 6
## Escalate if: public API behaviour is ambiguous and needs product decision
