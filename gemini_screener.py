"""Strict Gemini translation layer for free-form Screener requests."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from screener_service import FIELD_LABELS, FundamentalRule


DEFAULT_MODEL = "gemini-3.5-flash-lite"
_ALLOWED_OPERATORS = {"<", "<=", ">", ">="}
_MAX_QUERY_LENGTH = 400


class GeminiScreenerError(RuntimeError):
    """Controlled error safe to show in the Streamlit interface."""


def translate_screener_request(query: str, api_key: str, model: str = DEFAULT_MODEL) -> tuple[list[FundamentalRule], str]:
    """Translate natural language into the local, allowlisted screener rule set."""
    request_text = query.strip()
    if not api_key.strip():
        raise GeminiScreenerError("Add GEMINI_API_KEY to Streamlit secrets to use AI interpretation.")
    if not request_text or len(request_text) > _MAX_QUERY_LENGTH:
        raise GeminiScreenerError("Describe the screen in 1 to 400 characters.")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": _prompt(request_text)}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": _response_schema(),
        },
    }
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    try:
        request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
    except (HTTPError, URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise GeminiScreenerError("Gemini could not interpret the screen right now. Try again shortly.") from error
    return validate_gemini_screen(result)


def validate_gemini_screen(payload: object) -> tuple[list[FundamentalRule], str]:
    """Treat Gemini output as untrusted and reduce it to supported local filters."""
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise GeminiScreenerError("Gemini returned an unsupported screen.")
    rules: list[FundamentalRule] = []
    for raw_rule in payload["rules"]:
        if not isinstance(raw_rule, dict):
            raise GeminiScreenerError("Gemini returned an unsupported rule.")
        field, operator, value = raw_rule.get("field"), raw_rule.get("operator"), raw_rule.get("value")
        if field not in FIELD_LABELS or operator not in _ALLOWED_OPERATORS:
            raise GeminiScreenerError("Gemini requested a metric that is not available in this screener.")
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as error:
            raise GeminiScreenerError("Gemini returned an invalid numeric rule.") from error
        if not 0 <= numeric_value <= 10_000_000:
            raise GeminiScreenerError("Gemini returned a value outside this screener's safe range.")
        rules.append(FundamentalRule(field, operator, numeric_value))
    if not rules or len(rules) > 5:
        raise GeminiScreenerError("Ask for one to five supported fundamental conditions.")
    summary = payload.get("summary")
    if not isinstance(summary, str):
        summary = "AI interpreted your request into supported fundamental rules."
    return rules, summary[:240]


def _prompt(query: str) -> str:
    fields = ", ".join(f"{name}: {label}" for name, label in FIELD_LABELS.items())
    return (
        "Convert the user's Indian-equity screener request into only the allowed filters. "
        "Do not provide investment advice, stock picks, explanations of data, or unsupported metrics. "
        "Market cap values must be in INR crore; ROE and dividend yield values must be percentages. "
        f"Allowed fields: {fields}. Allowed operators: <, <=, >, >=. "
        f"User request: {query}"
    )


def _response_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "enum": list(FIELD_LABELS)},
                        "operator": {"type": "string", "enum": sorted(_ALLOWED_OPERATORS)},
                        "value": {"type": "number"},
                    },
                    "required": ["field", "operator", "value"],
                },
                "minItems": 1,
                "maxItems": 5,
            },
            "summary": {"type": "string"},
        },
        "required": ["rules", "summary"],
    }
