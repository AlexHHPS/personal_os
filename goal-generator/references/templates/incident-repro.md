# Template: incident-repro

## Purpose
Reproduce a production incident in staging and produce a structured
reproduction report with evidence: error logs, stack trace, HTTP request
that triggers the issue, and screenshot if UI-visible.

## Done when
`[repro_command]` produces the same error signature as the incident
AND `incident-repro/evidence/` contains: error.log, repro_request.curl, stack_trace.txt
AND `incident-repro/REPORT.md` exists with root cause hypothesis

## Standard constraints
- Use staging or local environment only — never reproduce against production
- Do not fix the issue in this loop — only reproduce and document
- Evidence files must be committed to a repro/ branch

## Typical MAX_ATTEMPTS: 8
## Escalate if: incident cannot be reproduced in staging after 5 attempts (env diff likely)
