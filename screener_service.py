"""Yahoo fundamental enrichment and safe free-text rules for the Streamlit screener."""
from __future__ import annotations

from dataclasses import dataclass
import re

import pandas as pd

from yahoo_chart_service import YahooChartError, yahoo_symbol


@dataclass(frozen=True)
class FundamentalRule:
    field: str
    operator: str
    value: float


FIELD_LABELS = {
    "pe": "P/E",
    "pb": "P/B",
    "roe": "ROE %",
    "dividend_yield": "Dividend yield %",
    "market_cap_cr": "Market cap (Rs Cr)",
}

_ALIASES = {
    "market cap": "market_cap_cr",
    "marketcap": "market_cap_cr",
    "mcap": "market_cap_cr",
    "dividend yield": "dividend_yield",
    "dividend": "dividend_yield",
    "p/e": "pe",
    "pe": "pe",
    "price to book": "pb",
    "p/b": "pb",
    "pb": "pb",
    "return on equity": "roe",
    "roe": "roe",
}
_OPERATOR_ALIASES = {
    "<": "<", "under": "<", "below": "<", "less than": "<",
    "<=": "<=", "at most": "<=",
    ">": ">", "above": ">", "over": ">", "more than": ">",
    ">=": ">=", "at least": ">=",
}
_RULE_PATTERN = re.compile(
    r"(?P<field>market\s*cap|marketcap|mcap|dividend\s*yield|dividend|p/e|pe|price\s*to\s*book|p/b|pb|return\s*on\s*equity|roe)"
    r"\s*(?:is|of|than)?\s*(?P<operator><=|>=|<|>|under|below|less\s+than|at\s+most|above|over|more\s+than|at\s+least)\s*"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|cr|crore|crores|bn|billion)?",
    re.IGNORECASE,
)


def parse_fundamental_query(query: str) -> list[FundamentalRule]:
    """Parse a deliberately limited, explainable query language into filters."""
    clean = query.strip().lower()
    if not clean:
        return []
    rules: list[FundamentalRule] = []
    for match in _RULE_PATTERN.finditer(clean):
        raw_field = re.sub(r"\s+", " ", match.group("field").lower())
        raw_operator = re.sub(r"\s+", " ", match.group("operator").lower())
        field = _ALIASES[raw_field]
        value = float(match.group("value"))
        unit = (match.group("unit") or "").lower()
        if field == "market_cap_cr":
            if unit in {"bn", "billion"}:
                value *= 100
            # Market cap rules are expressed in crore for Indian equities.
        rules.append(FundamentalRule(field, _OPERATOR_ALIASES[raw_operator], value))
    if not rules:
        raise ValueError("Try a rule such as: PE under 25 and ROE above 15%.")
    return rules


def filter_fundamentals(frame: pd.DataFrame, rules: list[FundamentalRule]) -> pd.DataFrame:
    """Apply parsed fundamental rules without treating missing provider values as matches."""
    result = frame.copy()
    for rule in rules:
        values = pd.to_numeric(result[rule.field], errors="coerce")
        if rule.operator == "<":
            result = result[values < rule.value]
        elif rule.operator == "<=":
            result = result[values <= rule.value]
        elif rule.operator == ">":
            result = result[values > rule.value]
        else:
            result = result[values >= rule.value]
    return result


def fetch_yahoo_fundamentals(public_symbols: tuple[str, ...]) -> pd.DataFrame:
    """Read Yahoo fundamentals for a bounded shortlist; caller controls caching and size."""
    try:
        import yfinance as yf
    except ImportError as error:
        raise YahooChartError("Yahoo Finance is not installed.") from error
    rows: list[dict] = []
    for public_symbol in public_symbols:
        try:
            info = yf.Ticker(yahoo_symbol(public_symbol)).get_info()
        except Exception:
            continue
        if not isinstance(info, dict):
            continue
        rows.append({
            "Symbol": public_symbol,
            "pe": info.get("trailingPE"),
            "pb": info.get("priceToBook"),
            "roe": _percentage(info.get("returnOnEquity")),
            "dividend_yield": _percentage(info.get("dividendYield")),
            "market_cap_cr": _crore(info.get("marketCap")),
        })
    if not rows:
        raise YahooChartError("Yahoo Finance could not provide fundamentals for this shortlist.")
    return pd.DataFrame(rows)


def _percentage(value: object) -> float | None:
    try:
        return float(value) * 100
    except (TypeError, ValueError):
        return None


def _crore(value: object) -> float | None:
    try:
        return float(value) / 10_000_000
    except (TypeError, ValueError):
        return None
