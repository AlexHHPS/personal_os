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

GOAL=$(claude --skip-permissions -p "$SKILL_INVOKE" 2>/dev/null)
[ -n "$GOAL" ] || { echo "ERROR: empty output from skill." >&2; exit 1; }

if python3 "$VALIDATE_SCRIPT" "$GOAL" > /dev/null 2>&1; then
  echo "$GOAL"
else
  echo "ERROR: goal failed validation:" >&2
  python3 "$VALIDATE_SCRIPT" "$GOAL" >&2
  exit 1
fi
