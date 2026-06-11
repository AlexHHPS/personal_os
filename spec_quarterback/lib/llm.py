"""Shared OmniRoute (OpenAI-compatible) call helpers.

Both flows talk to OmniRoute the same way:

* the **generator** (``lib.generator``) issues one structured call
  (PRD -> ``SpecList``);
* the **refiner** (``lib.refiner``) issues free-markdown critique calls and
  structured improve/score calls.

These helpers centralise the request shape so the two flows stay DRY:

* structured calls bind ``response_format=json_schema`` to a
  Pydantic-derived JSON Schema (flattened + pattern-stripped by
  ``FlatSchemaMixin``) and validate the response client-side, retrying
  once with the validation error fed back into the conversation;
* free-markdown calls just return the message content verbatim.

Extracted from the dissolved 8-call ``orchestrator._call_structured`` /
``_call_freeform`` so both the generator and the refiner can reuse them.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Final, TypeVar, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema
from pydantic import BaseModel, ValidationError

from spec_quarterback.lib.json_extract import extract_json, parse_model

logger = logging.getLogger(__name__)

# 3.11-safe generic: replaces the PEP 695 ``[T: BaseModel]`` parameter lists on
# the call helpers below so the package installs on a Python 3.11 interpreter
# (the Railway Hermes venv) as well as the 3.13 Brein venv.
T = TypeVar("T", bound=BaseModel)

# One retry mirrors the original design: a second failure surfaces the
# upstream defect to the operator rather than looping forever.
DEFAULT_MAX_VALIDATION_RETRIES: Final[int] = 1


async def call_structured(
    *,
    client: AsyncOpenAI,
    model: str,
    system: str,
    user: str,
    temperature: float,
    schema_cls: type[T],
    max_retries: int = DEFAULT_MAX_VALIDATION_RETRIES,
) -> T:
    """Issue a structured-output call; validate; retry once on ValidationError.

    Args:
        client: OpenAI-compatible client pointed at OmniRoute.
        model: Model id forwarded as ``model`` (e.g. ``hermes-combo``).
        system: System prompt.
        user: User prompt.
        temperature: Sampling temperature.
        schema_cls: Pydantic model the response must validate against. Its
            ``model_json_schema()`` is embedded in ``response_format``.
        max_retries: Retries after a Pydantic ``ValidationError`` before
            re-raising.

    Returns:
        A validated ``schema_cls`` instance.

    Raises:
        ValidationError: Final validation failure after exhausting retries.
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    schema_payload: dict[str, Any] = {
        "type": "json_schema",
        "json_schema": {
            "name": schema_cls.__name__,
            "strict": True,
            "schema": schema_cls.model_json_schema(),
        },
    }

    last_error: ValidationError | None = None
    for attempt in range(max_retries + 1):
        response = await client.chat.completions.create(
            model=model,
            messages=cast(list[ChatCompletionMessageParam], messages),
            temperature=temperature,
            response_format=cast(ResponseFormatJSONSchema, schema_payload),
        )
        raw = response.choices[0].message.content or ""
        try:
            return schema_cls.model_validate_json(raw)
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "[llm] %s validation failed (attempt %d/%d): %s",
                schema_cls.__name__,
                attempt + 1,
                max_retries + 1,
                exc,
            )
            if attempt >= max_retries:
                raise
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous output failed Pydantic validation against the "
                        f"{schema_cls.__name__} schema with the following errors:\n\n{exc}\n\n"
                        "Emit a corrected version that satisfies the schema. "
                        "Output raw JSON only, no markdown fences."
                    ),
                }
            )
    raise RuntimeError(  # pragma: no cover - unreachable; loop returns or raises
        f"validation retry exhausted for {schema_cls.__name__}"
    ) from last_error


async def call_freeform(
    *,
    client: AsyncOpenAI,
    model: str,
    system: str,
    user: str,
    temperature: float,
) -> str:
    """Issue a non-structured call; return the raw message content."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    response = await client.chat.completions.create(
        model=model,
        messages=cast(list[ChatCompletionMessageParam], messages),
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


DEFAULT_CALL_RETRIES: Final[int] = 1


def _looks_usable(raw: str) -> bool:
    """True when ``raw`` carries a non-empty JSON object we can validate.

    A transient empty/garbled response (seen under concurrent load against a
    local model) extracts to ``{}`` or non-JSON; that is worth one retry before
    accepting the lenient default. A non-empty object — even with field drift —
    is kept (the schema heals it; the critic grades it).
    """
    try:
        obj = json.loads(extract_json(raw))
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(obj, dict) and len(obj) > 0


async def call_model(
    *,
    client: AsyncOpenAI,
    model: str,
    system: str,
    user: str,
    temperature: float,
    schema_cls: type[T],
    retries: int = DEFAULT_CALL_RETRIES,
) -> T:
    """Free-form JSON call parsed leniently into ``schema_cls`` — never raises.

    The SDD flow uses this instead of :func:`call_structured`: the model is
    asked for raw JSON (see the generation/critic prompts) and the response is
    parsed by :func:`parse_model`, which tolerates fences, prose, and field
    drift and falls back to a default-healed instance rather than failing. This
    keeps the pipeline running on imperfect model output and sidesteps the GBNF
    grammar limitations of constrained decoding on nested schemas.

    A response that is not a non-empty JSON object is retried up to ``retries``
    times before accepting the lenient fallback — this recovers the occasional
    empty/garbled response without ever raising.
    """
    raw = ""
    for attempt in range(retries + 1):
        raw = await call_freeform(
            client=client, model=model, system=system, user=user, temperature=temperature
        )
        if _looks_usable(raw):
            return parse_model(raw, schema_cls)
        logger.warning(
            "[llm] %s: empty/garbled response (attempt %d/%d)",
            schema_cls.__name__,
            attempt + 1,
            retries + 1,
        )
    return parse_model(raw, schema_cls)
