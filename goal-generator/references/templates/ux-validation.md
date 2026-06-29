# Template: ux-validation

## Purpose
Validate a UI flow with a Playwright/ProofShot agent: navigate the flow,
capture screenshots at key steps, check accessibility, and produce a
structured validation report.

## Done when
`cat ux-validation/SUMMARY.md | grep "PASS" | wc -l` equals [expected_pass_count]
AND `cat ux-validation/SUMMARY.md | grep "FAIL" | wc -l` outputs 0
AND `ux-validation/step-*.png` files exist (at least [min_screenshots] screenshots)

## Standard constraints
- Test against [env: staging | localhost | preview] only — never production
- Do not create, modify, or delete any data unless explicitly stated
- Screenshots must include: page title, URL bar, timestamp overlay

## Typical MAX_ATTEMPTS: 8
## Escalate if: auth flow fails (can't log in to run the test at all)
