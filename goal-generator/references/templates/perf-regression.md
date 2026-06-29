# Template: perf-regression

## Purpose
Detect and fix a performance regression vs a known baseline.

## Done when
`[benchmark_command] | jq .p95_ms` outputs a value < [threshold]
AND `[test_runner]` exits with 0

## Standard constraints
- Only modify code in [scope_path]
- Do not change public API contracts
- Benchmark must be run under the same conditions as the baseline (same Docker stack, same dataset)

## Typical MAX_ATTEMPTS: 10
## Escalate if: profiler shows regression is in a third-party dependency
