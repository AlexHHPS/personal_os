# Template: ab-test-setup

## Purpose
Wire up a feature flag and set up A/B test infrastructure: flag created,
variant logic in code, analytics events firing, and baseline metric snapshot taken.

## Done when
`curl -s [flag_endpoint] | jq .[flag_name].enabled` outputs true
AND `[analytics_event_test]` confirms both variant A and variant B events fire
AND `[test_runner]` exits with 0

## Standard constraints
- Feature flag must default to OFF (control = 100%) on creation
- Do not enable the flag for real users — only in test environment
- Variant B must be in [scope_path] only

## Typical MAX_ATTEMPTS: 8
## Escalate if: analytics provider API is unreachable
