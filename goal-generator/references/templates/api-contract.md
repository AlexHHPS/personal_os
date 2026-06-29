# Template: api-contract

## Purpose
Verify an API contract (OpenAPI spec, Pact file, or snapshot) has not changed
after a refactor. If it has changed, update the contract and notify consumers.

## Done when
`[contract_tool] verify [spec_file]` exits with 0
AND diff between old and new spec shows only additive changes (no removed fields)

## Standard constraints
- Breaking changes (removed fields, changed types) require human approval before proceeding
- Do not modify consumer code — only producer

## Typical MAX_ATTEMPTS: 6
## Escalate if: breaking change detected (removed or renamed field in response)
