"""Tolerant JSON extraction for free-form model output.

The critic flow asks the model for "raw JSON only", but routed models still
occasionally wrap the payload in a ```json fence or prepend a sentence. The
refiner parses the critic verdict from a :func:`call_freeform` response (the
verdict schema is too deeply nested to bind safely as a constrained
``response_format`` call — see ``schema_flatten`` for the GBNF limitation), so
it needs to recover the JSON object from imperfect text before validating it.

:func:`extract_json` returns the most likely JSON substring; the caller then
runs ``model_validate_json`` on it.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 3.11-safe generic: replaces the PEP 695 ``def parse_model[T: BaseModel]``
# parameter list so the package installs on a Python 3.11 interpreter (the
# Railway Hermes venv) as well as the 3.13 Brein venv.
T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*(?P<body>.*?)\s*```", re.DOTALL | re.IGNORECASE)
_CTRL = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def repair_json(text: str) -> str:
    """Best-effort repair of the common LLM JSON corruptions — never raises.

    A single scan that tolerates the malformations local models emit and the strict
    ``json`` parser rejects: single-quoted strings, unescaped inner quotes, raw control
    characters inside strings, trailing commas, a dangling ``key:`` with no value, and
    truncation (an unterminated string and/or unclosed brackets at end-of-text). It only
    *narrows toward valid JSON*; the caller still validates the result, and any residual
    invalidity falls through to the empty-default instance. This recovers a near-miss
    verdict instead of discarding it — in the spirit of "degrade, never hard-stop".
    """
    s = text.strip()
    out: list[str] = []
    stack: list[str] = []  # expected closers, e.g. "}" / "]"
    quote = ""  # current string delimiter (" or '), or "" when outside a string
    escape = False
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if quote:
            if escape:
                out.append(ch)
                escape = False
            elif ch == "\\":
                out.append(ch)
                escape = True
            elif ch == quote:
                # Closing quote, or an unescaped inner quote? Peek the next non-space:
                # a real close is followed by a structural char (or end-of-text).
                j = i + 1
                while j < n and s[j] in " \t\r\n":
                    j += 1
                nxt = s[j] if j < n else ""
                if nxt in (",", "}", "]", ":", ""):
                    out.append('"')  # always normalise to a double quote
                    quote = ""
                else:
                    out.append('\\"')  # inner literal quote → escape it
            elif ch == '"':
                out.append('\\"')  # a double quote inside a single-quoted string
            elif ch in _CTRL:
                out.append(_CTRL[ch])  # escape a raw control char
            else:
                out.append(ch)
        else:
            if ch in ('"', "'"):
                quote = ch
                out.append('"')
            elif ch in "{[":
                out.append(ch)
                stack.append("}" if ch == "{" else "]")
            elif ch in "}]":
                if stack:
                    stack.pop()
                    out.append(ch)
                # a stray closer with nothing open → drop it
            else:
                out.append(ch)
        i += 1

    if quote:
        out.append('"')  # close an unterminated string (truncation)
    result = "".join(out).rstrip()
    if result.endswith(":"):
        result += " null"  # dangling key with no value
    result = re.sub(r",\s*$", "", result)  # drop a trailing comma before we close
    result += "".join(reversed(stack))  # close any brackets left open (truncation)
    return _TRAILING_COMMA_RE.sub(r"\1", result)  # remove commas now sitting before a closer


def extract_json(text: str) -> str:
    """Return the best-effort JSON object substring from ``text``.

    Strategy, in order:
      1. If a ```json ... ``` (or bare ``` ... ```) fence is present, use its body.
      2. Otherwise slice from the first ``{`` to the last ``}``.
      3. Otherwise return the stripped input unchanged (let the caller's
         validation raise a meaningful error).

    This never raises — it only narrows the text. JSON validity is the
    caller's concern (``model_validate_json``).
    """
    stripped = text.strip()

    fence = _FENCE_RE.search(stripped)
    if fence:
        stripped = fence.group("body").strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def parse_model(raw: str, schema_cls: type[T]) -> T:
    """Parse free-form model output into ``schema_cls`` — never raises.

    The whole flow runs through LLMs, so the response may carry fences, prose,
    or field drift. The resolution order, each tolerant of the last failing:
      1. extract the JSON substring and ``model_validate_json`` it;
      2. ``json.loads`` then ``model_validate`` (handles some odd encodings);
      3. ``repair_json`` the substring (close strings/brackets, fix quotes,
         strip trailing commas) then validate — recovers a malformed-but-near
         response instead of discarding it;
      4. fall back to ``model_validate({})`` — a default-healed instance — so
         the pipeline keeps going (the critic will flag the empty document)
         rather than crashing on a malformed response.

    The schemas are deliberately lenient (optional fields + ``mode="before"``
    healers), so step 1 succeeds for any well-formed JSON object even with
    missing or mistyped fields.
    """
    text = extract_json(raw)
    try:
        return schema_cls.model_validate_json(text)
    except Exception as exc:  # resilience: any parse issue degrades gracefully
        logger.warning("[parse_model] %s json validate failed: %s", schema_cls.__name__, exc)
    try:
        return schema_cls.model_validate(json.loads(text))
    except Exception as exc:  # try a repair pass before giving up
        logger.warning("[parse_model] %s dict validate failed: %s", schema_cls.__name__, exc)
    try:
        model = schema_cls.model_validate(json.loads(repair_json(text)))
        logger.info("[parse_model] %s recovered via JSON repair", schema_cls.__name__)
        return model
    except Exception as exc:  # last-resort fallback below
        logger.warning("[parse_model] %s repair failed: %s", schema_cls.__name__, exc)
    logger.warning("[parse_model] %s falling back to empty/default instance", schema_cls.__name__)
    return schema_cls.model_validate({})
