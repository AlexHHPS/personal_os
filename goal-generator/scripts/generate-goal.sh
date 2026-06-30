#!/usr/bin/env bash
# generate-goal.sh - Programmatic goal generation + validation.
# Usage: ./generate-goal.sh <task_type> "<task_description>" [--dry-run]
set -euo pipefail

TASK_TYPE="${1:-custom}"
TASK_DESC="${2:-}"
DRY_RUN="${3:-}"
VALIDATE_SCRIPT="$(dirname "$0")/validate_goal.py"

[ -n "$TASK_DESC" ] || { echo "ERROR: task description required." >&2; exit 1; }

SKILL_INVOKE="/goal-generator $TASK_TYPE \"$TASK_DESC\""
[ "$DRY_RUN" = "--dry-run" ] && { echo "[DRY RUN] $SKILL_INVOKE"; exit 0; }

RAW=$(claude --skip-permissions -p "$SKILL_INVOKE" 2>/dev/null)
[ -n "$RAW" ] || { echo "ERROR: empty output from skill." >&2; exit 1; }

# The skill emits the goal inside a ```goal fenced block, then a quality report.
# Extract just the goal; fall back to the raw output for older skill versions.
GOAL=$(printf '%s\n' "$RAW" | awk '/^```goal[[:space:]]*$/{f=1;next} /^```/{f=0} f' | sed '/^📄 Plan:/d')
[ -n "$GOAL" ] || GOAL="$RAW"

# Print the skill's quality report (score + follow-up questions) to stderr so it
# stays visible without polluting the goal captured from stdout.
printf '%s\n' "$RAW" | awk '/^## 📊/{f=1} f' >&2 || true

if python3 "$VALIDATE_SCRIPT" "$GOAL" >&2; then
  echo "$GOAL"
else
  echo "ERROR: goal failed validation (see report above)." >&2
  exit 1
fi
