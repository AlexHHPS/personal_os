#!/usr/bin/env python3
"""
validate_goal.py - Validates a /goal prompt before it enters an agent loop.
Usage: python validate_goal.py "<goal_string>"
Exit 0: valid. Exit 1: invalid.
Always prints a quality score (NN/100) so callers can report it.
"""
import sys, re

SUBJECTIVE_WORDS = [
    "better", "cleaner", "improved", "good", "nice", "quality",
    "readable", "maintainable", "elegant", "solid", "proper"
]
VAGUE_OPENERS = ["make sure", "ensure", "try to", "attempt to", "do your best"]
# Compact inline goals (no plan document) should stay tight.
MAX_INLINE_LENGTH = 500
# Hard cap: the goal prompt is copied & pasted into a loop, so newlines count.
# Anything bigger must be offloaded to a /plan-backed document and referenced.
MAX_GOAL_PROMPT_LENGTH = 4000


def assess(goal: str) -> dict:
    """Score a goal against the same rubric as SKILL.md Step 5.

    Returns {dimension: (passed: bool, weight: int, note: str)}.
    """
    g = goal.strip()
    checks: dict = {}

    # Proof command: backtick shell command OR MCP tool call pattern (25)
    has_shell_cmd = bool(re.search(r"`[^`]+`", g))
    has_mcp_call = bool(re.search(
        r"linear\.\w+|gh \w+|curl |jq |hyperfine|proofshot|k6 run|playwright|pgbench|lighthouse", g))
    checks["proof-command"] = (
        has_shell_cmd or has_mcp_call, 25,
        "shell/MCP command present" if has_shell_cmd or has_mcp_call
        else "no shell command or MCP call found",
    )

    # Expected output is concrete (20)
    expected_keywords = ["outputs", "exits with", "contains", "returns",
                         "shows", "reports", "equals", "outputs true", "non-empty"]
    has_expected = any(k in g.lower() for k in expected_keywords)
    checks["expected-output"] = (
        has_expected, 20,
        "concrete expected output stated" if has_expected
        else "no concrete expected output stated",
    )

    # Constraints prevent scope creep (20)
    constraint_keywords = ["must not", "without", "do not", "only files", "only in",
                           "no changes", "no new", "scope:", "do not modify",
                           "only create", "constraints:"]
    has_constraint = any(k in g.lower() for k in constraint_keywords)
    checks["constraint"] = (
        has_constraint, 20,
        "constraint present" if has_constraint else "no constraint found",
    )

    # Stop conditions: MAX_ATTEMPTS + ESCALATE_IF (15)
    has_max = bool(re.search(r"max[_ ]?attempts|max:\s*\d", g, re.I))
    has_esc = bool(re.search(r"escalate[_ ]?if|esc:", g, re.I))
    checks["stop-conditions"] = (
        has_max and has_esc, 15,
        "max attempts + escalate present"
        if has_max and has_esc
        else f"missing {'MAX_ATTEMPTS' if not has_max else ''}"
             f"{' and ' if not has_max and not has_esc else ''}"
             f"{'ESCALATE_IF' if not has_esc else ''}".strip(),
    )

    # Free of subjective / vague language (10)
    found_subj = [w for w in SUBJECTIVE_WORDS if w in g.lower()]
    starts_vague = any(g.lower().startswith(o) for o in VAGUE_OPENERS)
    clean_language = not found_subj and not starts_vague
    note = "no subjective/vague language"
    if found_subj:
        note = f"remove subjective words: {found_subj}"
    elif starts_vague:
        note = "starts with a vague opener (make sure/ensure/...)"
    checks["language"] = (clean_language, 10, note)

    # Within length budget & right form (10)
    within_hard = len(g) < MAX_GOAL_PROMPT_LENGTH
    references_plan = bool(
        re.search(r"docs/goals/[\w./-]+\.md|execute the plan|plan in ", g, re.I))
    is_long_form = "## Done when" in g
    within_inline = references_plan or is_long_form or len(g) <= MAX_INLINE_LENGTH
    if not within_hard:
        len_note = (f"{len(g)} chars >= {MAX_GOAL_PROMPT_LENGTH}: offload detail to a "
                    "/plan doc and reference docs/goals/<slug>-plan.md")
    elif not within_inline:
        len_note = (f"{len(g)} chars > {MAX_INLINE_LENGTH} inline: use a plan-backed "
                    "goal that references docs/goals/<slug>-plan.md")
    else:
        len_note = f"{len(g)} chars, correct form"
    checks["length-form"] = (within_hard and within_inline, 10, len_note)

    return checks


def score(checks: dict) -> int:
    return sum(weight for passed, weight, _ in checks.values() if passed)


def validate(goal: str) -> list:
    """Backward-compatible: returns a list of FAIL messages (empty == valid)."""
    return [
        f"FAIL [{dim}]: {note}"
        for dim, (passed, _weight, note) in assess(goal).items()
        if not passed
    ]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_goal.py \"<goal_string>\"")
        sys.exit(2)
    goal_input = " ".join(sys.argv[1:])
    checks = assess(goal_input)
    total = score(checks)
    errors = [f"FAIL [{d}]: {n}" for d, (p, _w, n) in checks.items() if not p]

    print(f"QUALITY_SCORE: {total}/100")
    for dim, (passed, weight, note) in checks.items():
        mark = "✓" if passed else "✗"
        earned = weight if passed else 0
        print(f"  {mark} {dim} ({earned}/{weight}): {note}")

    if errors:
        print(f"\nINVALID GOAL ({len(goal_input)} chars):")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print(f"\nVALID ({len(goal_input)} chars).")
        print(goal_input)
        sys.exit(0)
