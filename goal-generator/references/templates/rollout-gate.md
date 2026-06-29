# Template: rollout-gate

## Purpose
Run progressive rollout health checks before increasing a feature flag
percentage: error rate, p95 latency, and key business metric must be
within thresholds before proceeding.

## Done when
`[metrics_command] | jq .error_rate` outputs < [max_error_rate]
AND `[metrics_command] | jq .p95_ms` outputs < [p95_threshold]
AND `[metrics_command] | jq .[business_metric]` outputs within [range]

## Standard constraints
- Do not increase flag percentage if any gate fails
- Post Slack notification to [channel] before and after each percentage increase
- Rollback command must be documented in the goal output

## Typical MAX_ATTEMPTS: 5 (one per rollout step: 1% → 5% → 10% → 25% → 100%)
## Escalate if: error rate doubles vs baseline at any rollout step
