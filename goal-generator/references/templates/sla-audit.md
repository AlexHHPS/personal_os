# Template: sla-audit

## Purpose
Audit a service against its SLA definition: check p99 latency, uptime, and
error rate over [time_window], compare against SLA thresholds, produce a
pass/fail report, and open a Linear ticket for each breach.

## Done when
`jq .overall_verdict sla-audit/report.json` outputs "PASS" or "BREACH"
AND for each breach: `linear.get_issues` shows a new ticket with label "sla-breach"
AND `sla-audit/report.json` contains all three metrics: latency, uptime, error_rate

## Standard constraints
- Query metrics from [observability_tool: Datadog | Grafana | CloudWatch] only
- Do not modify application code — only audit and report
- Time window must be exactly [time_window: 7d | 30d | 90d]

## Typical MAX_ATTEMPTS: 4
## Escalate if: observability API is unreachable or returns incomplete data
