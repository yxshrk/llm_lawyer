"""Helpers for requesting JSON output from the LLM with graceful fallback.

OpenAI (and Gemini via compat, Groq partial) support response_format=json_object,
but we stay compatible with all three providers by asking for JSON in the prompt
and parsing the first {...} or [...] block.
"""
import json
import re
from typing import Any


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from a free-form LLM response."""
    if not text:
        return None
    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    # Try straight parse first
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    # Find the first {...} or [...] block
    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                continue
    return None
