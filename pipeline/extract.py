"""The model call.

Structured output is forced through tool use rather than requested in prose.
The model is given exactly one tool whose input schema is the Pydantic model,
and tool_choice pins it to that tool. The result is that the model cannot
reply with a paragraph you then have to parse. You get structured data or an
error, which is a much better failure mode.
"""

from __future__ import annotations

import os
import time
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

MODEL = os.environ.get("EXTRACTION_MODEL", "claude-sonnet-5")

# USD per million tokens. Verified September 2026 against public pricing.
# Put the date in this comment and re-check it before you quote a cost
# number in an interview.
PRICING = {
    "claude-sonnet-5":            {"input": 2.00, "output": 10.00},
    "claude-haiku-4-5-20251001":  {"input": 1.00, "output": 5.00},
    "claude-opus-5":              {"input": 5.00, "output": 25.00},
}

SYSTEM = """You extract structured data from creator partnership contracts and \
invoices for a beauty brand's marketing operations team.

Rules:
- Report only what the document states. If a field is not present, return null.
- Never infer a value from context or from what seems typical for this kind of \
document. A missing contract reference is null, not a guess.
- For monetary amounts, return a number. Convert amounts written in words, such \
as "four thousand five hundred dollars", to 4500.
- Copy names exactly as written, including suffixes such as LLC or Inc.
- If an agency is billing on behalf of a creator, record both names separately."""

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def usage_cost(usage: Any, model: str = MODEL) -> float:
    rates = PRICING.get(model)
    if rates is None:
        return 0.0
    return (usage.input_tokens * rates["input"]
            + usage.output_tokens * rates["output"]) / 1_000_000


def extract(
    content_blocks: list[dict],
    schema: type[T],
    label: str,
    model: str = MODEL,
    retries: int = 2,
) -> tuple[T, float]:
    """Run one extraction. Returns (parsed_model, cost_usd).

    Validation errors get one retry with the error fed back, because a model
    that returned a malformed date usually fixes it when told. Anything that
    still fails raises, and the eval harness records it as a hard error.
    Hard error rate is a number worth reporting rather than hiding.
    """
    tool = {
        "name": f"record_{label}",
        "description": f"Record every field found in the {label}.",
        "input_schema": schema.model_json_schema(),
    }
    messages: list[dict] = [{"role": "user", "content": content_blocks}]
    total_cost = 0.0
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        response = client().messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=messages,
        )
        total_cost += usage_cost(response.usage, model)
        block = next(b for b in response.content if b.type == "tool_use")
        try:
            return schema.model_validate(block.input), total_cost
        except ValidationError as exc:
            last_error = exc
            if attempt == retries:
                break
            messages += [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": [{
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "is_error": True,
                    "content": f"Validation failed: {exc}. Call the tool again with corrected values.",
                }]},
            ]
            time.sleep(0.5)

    raise RuntimeError(f"{label} extraction failed validation after {retries + 1} attempts: {last_error}")
