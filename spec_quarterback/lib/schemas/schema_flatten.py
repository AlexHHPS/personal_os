"""Workaround for llama.cpp / Ollama JSON-Schema → GBNF grammar bugs.

Ollama compiles ``response_format`` JSON Schemas (and the ``format`` field
on ``/api/chat``) to GBNF grammars via llama.cpp's
``json_schema_to_grammar.cpp``. Multiple upstream defects make non-trivial
schemas unsafe for constrained generation:

1. ``$defs`` / ``$ref`` resolution
   - ``ggml-org/llama.cpp#21228`` (Ollama issue ``ollama#8444``): the
     ``$defs`` / ``$ref`` resolver assigns the def in ``_refs`` *before*
     visiting it, so the emitted grammar depends on the alphabetical order
     of def names. Two semantically-identical schemas can produce one valid
     and one malformed grammar based purely on class-name ordering.
   - ``ollama#10805``: minified JSON schemas can be truncated mid-token
     during request serialization, producing parse errors like
     ``expecting ::= at ...key-elements-ha`` (truncated token).
   Mitigation: :func:`flatten_schema` inlines ``$ref`` recursively and
   drops ``$defs``.

2. ``pattern`` regex compilation
   llama.cpp's ``regex_to_grammar`` translation chokes on regexes
   containing character classes adjacent to repetition modifiers (e.g.
   ``[1-9][0-9]*``). Failure presents identically to the def-resolver
   bug — ``failed to load model vocabulary required for format`` HTTP 500
   — or, worse, Ollama silently degrades to ``format=""`` and proceeds
   with unconstrained generation.
   Mitigation: :func:`strip_unsupported_constraints` removes ``pattern``
   from the schema before sending. Pydantic still enforces patterns at
   ``model_validate`` time, so a malformed ID surfaces as a Pydantic
   ``ValidationError`` client-side rather than as silent acceptance.

The :class:`FlatSchemaMixin` applies both mitigations in
``model_json_schema()``.

When the upstream bugs ship a fix, delete this module and remove the
mixin from the four crew output classes.
"""

from __future__ import annotations

import copy
from typing import Any, cast

_REF_PREFIX = "#/$defs/"


def flatten_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` with all ``$defs`` / ``$ref`` inlined.

    The returned schema is semantically equivalent to the input but
    contains no ``$defs`` block and no ``$ref`` entries — all references
    are resolved into copies of their target definitions.

    Args:
        schema: A JSON Schema dict, typically from
            ``pydantic.BaseModel.model_json_schema()``.

    Returns:
        A new dict. The input is not mutated.

    Raises:
        ValueError: If a ``$ref`` points outside ``#/$defs/`` (external
            reference), names a missing def (dangling), or participates
            in a cycle along the resolution chain.
    """
    schema = copy.deepcopy(schema)
    defs: dict[str, Any] = schema.pop("$defs", {})
    # The root of a JSON Schema is always an object; _resolve only returns a
    # non-dict when it descends into list items or scalar leaves.
    return cast(dict[str, Any], _resolve(schema, defs, frozenset()))


def _resolve(node: Any, defs: dict[str, Any], seen: frozenset[str]) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            if not ref.startswith(_REF_PREFIX):
                raise ValueError(f"unsupported $ref (must start with {_REF_PREFIX!r}): {ref!r}")
            key = ref[len(_REF_PREFIX) :]
            if key in seen:
                raise ValueError(f"cycle detected in schema $defs at {key!r}")
            if key not in defs:
                raise ValueError(f"dangling $ref to missing def: {key!r}")
            return _resolve(defs[key], defs, seen | {key})
        return {k: _resolve(v, defs, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve(item, defs, seen) for item in node]
    return node


_UNSUPPORTED_GBNF_KEYS: frozenset[str] = frozenset({"pattern"})


def strip_unsupported_constraints(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` with GBNF-incompatible constraints removed.

    Currently strips:
        - ``pattern`` (llama.cpp's regex→GBNF translator is unreliable
          and the failure mode is silent format degradation; see module
          docstring).

    Constraints stripped here are still enforced by Pydantic at
    ``model_validate`` time, so the workaround does not weaken validation
    — it just moves enforcement from "Ollama refuses to emit invalid
    output" to "we reject invalid output after the fact".

    Args:
        schema: A JSON Schema dict, typically the output of
            :func:`flatten_schema`.

    Returns:
        A new dict. The input is not mutated.
    """
    return cast(dict[str, Any], _strip(schema))


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip(v) for k, v in node.items() if k not in _UNSUPPORTED_GBNF_KEYS}
    if isinstance(node, list):
        return [_strip(item) for item in node]
    return node


class FlatSchemaMixin:
    """Pydantic mixin that emits a GBNF-safe JSON Schema for Ollama.

    Apply to ``BaseModel`` subclasses whose schema is fed to Ollama's
    ``response_format`` (OpenAI-compat) or ``format`` (native /api/chat).
    The mixin applies two transformations in order:

        1. :func:`flatten_schema` — inlines ``$ref`` and drops ``$defs``.
        2. :func:`strip_unsupported_constraints` — removes ``pattern``.

    Usage::

        class CrewBrainOutput(FlatSchemaMixin, BaseModel):
            ...

    The mixin does not change the model's runtime validation behaviour;
    it only intercepts ``model_json_schema()``. Pattern validation still
    runs in ``model_validate``, so a Pydantic ``ValidationError`` on a
    malformed ID will surface client-side after the model returns.
    """

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raw = super().model_json_schema(*args, **kwargs)  # type: ignore[misc]
        return strip_unsupported_constraints(flatten_schema(raw))
