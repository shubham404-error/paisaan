"""Strict Gemini translation layer for free-form Screener requests."""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from screener_service import FIELD_LABELS, FundamentalRule


DEFAULT_MODEL = "gemini-3.5-flash-lite"
_ALLOWED_OPERATORS = {"<", "<=", ">", ">="}
_MAX_QUERY_LENGTH = 400
_MAX_TEXT_LENGTH = 280
_ADVICE_PATTERN = re.compile(r"\b(buy|sell|hold|accumulate|target price|price target|outperform|underperform|guaranteed)\b", re.IGNORECASE)
_LOW_VALUE_ACTION_PATTERN = re.compile(r"\bverify (open|high|low|close|previous close|volume|turnover)\b", re.IGNORECASE)
_COMPARISON_DIMENSIONS = {"price action", "valuation", "quality", "scale"}
_RESEARCH_FOCUSES = {"chart", "fundamentals", "disclosures"}


class GeminiScreenerError(RuntimeError):
    """Controlled error safe to show in the Streamlit interface."""


def translate_screener_request(query: str, api_key: str, model: str = DEFAULT_MODEL) -> tuple[list[FundamentalRule], str]:
    """Translate natural language into the local, allowlisted screener rule set."""
    request_text = query.strip()
    if not api_key.strip():
        raise GeminiScreenerError("Add GEMINI_API_KEY to Streamlit secrets to use AI interpretation.")
    if not request_text or len(request_text) > _MAX_QUERY_LENGTH:
        raise GeminiScreenerError("Describe the screen in 1 to 400 characters.")
    result = _generate_json(_prompt(request_text), _response_schema(), api_key, model)
    return validate_gemini_screen(result)


def build_research_shortlist(facts: dict, allowed_symbols: set[str], api_key: str, model: str = DEFAULT_MODEL) -> dict:
    """Return up to three research candidates drawn only from the supplied screen."""
    prompt = (
        "Use only this timestamped Nifty 200 screener facts packet. Select up to three contrasting RESEARCH candidates, "
        "not investment picks. For each, cite supplied metric field names, name one counterpoint or missing fact, and provide "
        "one next research action. Never use buy/sell/hold language or make a forecast.\nFACTS:\n"
        f"{json.dumps(facts, separators=(',', ':'), default=str)}"
    )
    return validate_research_shortlist(_generate_json(prompt, _shortlist_schema(), api_key, model), allowed_symbols)


def compare_research_stocks(facts: dict, allowed_symbols: set[str], api_key: str, model: str = DEFAULT_MODEL) -> dict:
    """Compare a user-selected set without choosing a winner or making a recommendation."""
    prompt = (
        "Compare only the user-selected Indian equities in this timestamped facts packet. The UI already shows raw values, so do NOT "
        "restate prices, daily changes, dates, exchange, series, open/high/low, or raw trading activity. Instead produce 1-3 decision "
        "lenses that explain what materially separates the names for research, then one concrete next research question per symbol. "
        "Use chart for technical follow-up, fundamentals for valuation/quality follow-up, or disclosures for company/sector verification. "
        "Never ask the user to verify a displayed number. Do not declare a winner, recommend a trade, forecast, or mention facts outside "
        "this packet.\nFACTS:\n"
        f"{json.dumps(facts, separators=(',', ':'), default=str)}"
    )
    return validate_research_comparison(_generate_json(prompt, _comparison_schema(), api_key, model), allowed_symbols)


def build_chart_research_cues(facts: dict, api_key: str, model: str = DEFAULT_MODEL) -> dict:
    """Convert supplied technical facts into research checks, never a directional call."""
    prompt = (
        "Use only the supplied timestamped chart facts. Return observable technical context, confirmation checks, and limitations. "
        "Do not predict direction, use investment advice, or add external facts.\nFACTS:\n"
        f"{json.dumps(facts, separators=(',', ':'), default=str)}"
    )
    return validate_chart_cues(_generate_json(prompt, _chart_schema(), api_key, model))


def ask_stock_comparison(question: str, yahoo_facts: dict, history: list[dict], api_key: str, model: str = DEFAULT_MODEL) -> str:
    """Answer a comparison question from the selected stocks' Yahoo-only fact packet."""
    clean_question = question.strip()
    if not clean_question or len(clean_question) > _MAX_QUERY_LENGTH:
        raise GeminiScreenerError("Ask a comparison question in 1 to 400 characters.")
    recent_history = history[-6:]
    prompt = (
        "You are a concise Indian-equity research assistant. Answer the user's comparison question using ONLY the Yahoo Finance "
        "facts for the selected stocks below. Do not mention missing data, generic disclaimers, exchange mechanics, or repeat a table. "
        "Be decisive about trade-offs: use 'if your priority is X, Y is stronger on the supplied data' when supported. Do not guarantee "
        "returns or invent facts. Keep the response to three short paragraphs or fewer.\n"
        f"SELECTED YAHOO FACTS:\n{json.dumps(yahoo_facts, separators=(',', ':'), default=str)}\n"
        f"RECENT CONVERSATION:\n{json.dumps(recent_history, separators=(',', ':'))}\n"
        f"USER QUESTION: {clean_question}"
    )
    response = _generate_text(prompt, api_key, model)
    if len(response) > 1200:
        raise GeminiScreenerError("Gemini returned an overly long comparison response.")
    return response


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


def validate_research_shortlist(payload: object, allowed_symbols: set[str]) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise GeminiScreenerError("Gemini returned an unsupported research shortlist.")
    candidates = payload["candidates"]
    if not 1 <= len(candidates) <= 3:
        raise GeminiScreenerError("Gemini must return one to three research candidates.")
    seen: set[str] = set()
    clean: list[dict] = []
    for item in candidates:
        if not isinstance(item, dict) or item.get("symbol") not in allowed_symbols or item["symbol"] in seen:
            raise GeminiScreenerError("Gemini returned a candidate outside this screen.")
        seen.add(item["symbol"])
        clean.append({
            "symbol": item["symbol"],
            "screen_evidence": _safe_text(item.get("screen_evidence")),
            "counterpoint": _safe_text(item.get("counterpoint")),
            "next_step": _safe_text(item.get("next_step")),
        })
    return {"candidates": clean}


def validate_research_comparison(payload: object, allowed_symbols: set[str]) -> dict:
    required = ("decision_lenses", "data_gaps", "research_actions")
    if not isinstance(payload, dict) or any(not isinstance(payload.get(key), list) for key in required):
        raise GeminiScreenerError("Gemini returned an unsupported comparison.")
    lenses: list[dict] = []
    for item in payload["decision_lenses"]:
        if not isinstance(item, dict) or item.get("dimension") not in _COMPARISON_DIMENSIONS:
            raise GeminiScreenerError("Gemini returned an unsupported comparison lens.")
        symbols = item.get("symbols")
        if not isinstance(symbols, list) or not symbols or not set(symbols).issubset(allowed_symbols):
            raise GeminiScreenerError("Gemini returned comparison evidence outside your selected stocks.")
        lenses.append({"dimension": item["dimension"], "symbols": symbols, "takeaway": _safe_text(item.get("takeaway"))})
    if not 1 <= len(lenses) <= 3:
        raise GeminiScreenerError("Gemini must return one to three comparison lenses.")
    actions: list[dict] = []
    seen: set[str] = set()
    for item in payload["research_actions"]:
        if not isinstance(item, dict) or item.get("symbol") not in allowed_symbols or item["symbol"] in seen:
            raise GeminiScreenerError("Gemini returned a comparison outside your selected stocks.")
        if item.get("focus") not in _RESEARCH_FOCUSES:
            raise GeminiScreenerError("Gemini returned an unsupported research action.")
        seen.add(item["symbol"])
        question, reason = _safe_text(item.get("question")), _safe_text(item.get("reason"))
        if _LOW_VALUE_ACTION_PATTERN.search(question) or _LOW_VALUE_ACTION_PATTERN.search(reason):
            raise GeminiScreenerError("Gemini returned a low-value research action.")
        actions.append({"symbol": item["symbol"], "focus": item["focus"], "question": question, "reason": reason})
    if seen != allowed_symbols:
        raise GeminiScreenerError("Gemini did not cover every selected stock.")
    return {
        "decision_lenses": lenses,
        "data_gaps": _safe_text_list(payload["data_gaps"]),
        "research_actions": actions,
    }


def validate_chart_cues(payload: object) -> dict:
    required = ("observations", "confirmation_checks", "limitations")
    if not isinstance(payload, dict) or any(not isinstance(payload.get(key), list) for key in required):
        raise GeminiScreenerError("Gemini returned unsupported chart cues.")
    return {
        "observations": _safe_text_list(payload["observations"]),
        "confirmation_checks": _optional_text_list(payload["confirmation_checks"]),
        "limitations": _optional_text_list(payload["limitations"]),
    }


def _safe_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > _MAX_TEXT_LENGTH or _ADVICE_PATTERN.search(value):
        raise GeminiScreenerError("Gemini returned content outside the research-only policy.")
    return value.strip()


def _safe_text_list(value: object) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 5:
        raise GeminiScreenerError("Gemini returned an unsupported research section.")
    return [_safe_text(item) for item in value]


def _optional_text_list(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 5:
        raise GeminiScreenerError("Gemini returned an unsupported research section.")
    return [_safe_text(item) for item in value]


def _generate_json(prompt: str, schema: dict, api_key: str, model: str) -> object:
    if not api_key.strip():
        raise GeminiScreenerError("Add GEMINI_API_KEY to Streamlit secrets to use AI research.")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": schema},
    }
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    try:
        request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        return json.loads(body["candidates"][0]["content"]["parts"][0]["text"])
    except (HTTPError, URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise GeminiScreenerError("Gemini research is temporarily unavailable. Try again shortly.") from error


def _generate_text(prompt: str, api_key: str, model: str) -> str:
    if not api_key.strip():
        raise GeminiScreenerError("Add GEMINI_API_KEY to Streamlit secrets to use AI research.")
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 500}}
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    try:
        request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=25) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body["candidates"][0]["content"]["parts"][0]["text"]
    except (HTTPError, URLError, TimeoutError, KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise GeminiScreenerError("Gemini comparison chat is temporarily unavailable. Try again shortly.") from error
    if not isinstance(text, str) or not text.strip():
        raise GeminiScreenerError("Gemini returned an empty comparison response.")
    return text.strip()


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


def _shortlist_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array", "minItems": 1, "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "screen_evidence": {"type": "string"},
                        "counterpoint": {"type": "string"},
                        "next_step": {"type": "string"},
                    },
                    "required": ["symbol", "screen_evidence", "counterpoint", "next_step"],
                },
            },
        },
        "required": ["candidates"],
    }


def _comparison_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "data_gaps": {"type": "array", "items": {"type": "string"}},
            "decision_lenses": {
                "type": "array", "minItems": 1, "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {"dimension": {"type": "string", "enum": sorted(_COMPARISON_DIMENSIONS)}, "symbols": {"type": "array", "items": {"type": "string"}}, "takeaway": {"type": "string"}},
                    "required": ["dimension", "symbols", "takeaway"],
                },
            },
            "research_actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}, "focus": {"type": "string", "enum": sorted(_RESEARCH_FOCUSES)}, "question": {"type": "string"}, "reason": {"type": "string"}},
                    "required": ["symbol", "focus", "question", "reason"],
                },
            },
        },
        "required": ["decision_lenses", "data_gaps", "research_actions"],
    }


def _chart_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "observations": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "confirmation_checks": {"type": "array", "items": {"type": "string"}},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["observations", "confirmation_checks", "limitations"],
    }
