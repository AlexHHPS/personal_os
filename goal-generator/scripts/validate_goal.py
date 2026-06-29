#!/usr/bin/env python3
"""
validate_goal.py - Validates a /goal prompt before it enters an agent loop.
Usage: python validate_goal.py "<goal_string>"
Exit 0: valid. Exit 1: invalid.
"""
import sys, re

SUBJECTIVE_WORDS = [
    "better", "cleaner", "improved", "good", "nice", "quality",
    "readable", "maintainable", "elegant", "solid", "proper"
]
VAGUE_OPENERS = ["make sure", "ensure", "try to", "attempt to", "do your best"]
MAX_GOAL_LENGTH = 500


def validate(goal: str) -> list:
    errors = []
    g = goal.strip()

    # Proof command: backtick shell command OR MCP tool call pattern
    has_shell_cmd = bool(re.search(r"`[^`]+`", g))
    has_mcp_call  = bool(re.search(r"linear\.\w+|gh \w+|curl |jq |hyperfine|proofshot|k6 run|playwright|pgbench|lighthouse", g))
    if not has_shell_cmd and not has_mcp_call:
        errors.append("FAIL [proof-command]: No shell command or MCP call found.")

    expected_keywords = ["outputs", "exits with", "contains", "returns", "shows", "reports", "equals", "outputs true", "non-empty"]
    if not any(k in g.lower() for k in expected_keywords):
        errors.append("FAIL [expected-output]: No expected output stated.")

    constraint_keywords = ["must not", "without", "do not", "only files", "only in",
                           "no changes", "no new", "scope:", "do not modify", "only create"]
    if not any(k in g.lower() for k in constraint_keywords):
        errors.append("FAIL [constraint]: No constraint found.")

    found_subj = [w for w in SUBJECTIVE_WORDS if w in g.lower()]
    if found_subj:
        errors.append(f"FAIL [subjective]: Remove: {found_subj}")

    for opener in VAGUE_OPENERS:
        if g.lower().startswith(opener):
            errors.append(f"FAIL [vague-opener]: Starts with: {opener!r}")
            break

    if "## Done when" not in g and len(g) > MAX_GOAL_LENGTH:
        errors.append(f"FAIL [length]: {len(g)} chars (max {MAX_GOAL_LENGTH}). Use long-form goal.md.")

    return errors


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_goal.py \"<goal_string>\"")
        sys.exit(2)
    goal_input = " ".join(sys.argv[1:])
    errors = validate(goal_input)
    if errors:
        print("INVALID GOAL:\n")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print(f"VALID ({len(goal_input)} chars).")
        print(goal_input)
        sys.exit(0)
