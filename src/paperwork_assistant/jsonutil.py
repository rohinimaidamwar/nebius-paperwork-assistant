from __future__ import annotations

import json
import re
from typing import Any


class ModelOutputError(ValueError):
    """The model did not return usable JSON."""


def strip_reasoning(text: str) -> str:
    """Remove <think>...</think> blocks that some reasoning models include."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"^.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()


def extract_json(text: str) -> dict[str, Any]:
    cleaned = strip_reasoning(text)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ModelOutputError("No JSON object found in model output")
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            raise ModelOutputError(f"Invalid JSON in model output: {e}") from e
    if not isinstance(value, dict):
        raise ModelOutputError("Model output JSON is not an object")
    return value
