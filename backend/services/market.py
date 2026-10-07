from __future__ import annotations

from datetime import datetime, timezone

from backend.core.cache import cache
from backend.core.config import get_settings
from backend.data.nse_provider import fetch_constituents, fetch_history, fetch_nifty_200_quotes


def overview() -> dict:
    settings = get_settings()
    key = "market:overview:nifty200"
    if cached := cache.get(key):
        return cached
    constituents = fetch_constituents()
    rows = fetch_nifty_200_quotes(constituents)
    advances = sum(1 for row in rows if row.get("pct_change", 0) > 0)
    declines = sum(1 for row in rows if row.get("pct_change", 0) < 0)
    latest_date = rows[0].get("date") if rows else None
    response = {
        "index": "NIFTY200",
        "as_of": latest_date,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source": "NSE Indices + NSE Bhavcopy MCP",
        "is_stale": False,
        "universe_count": len(rows),
        "breadth": {"advances": advances, "declines": declines, "unchanged": len(rows) - advances - declines},
        "average_change_pct": round(sum(row.get("pct_change", 0) for row in rows) / len(rows), 2) if rows else 0,
        "constituents": rows,
    }
    cache.set(key, response, settings.cache_ttl_seconds)
    return response


def bars(symbol: str, range_key: str) -> dict:
    months_by_range = {"1D": 1, "1W": 1, "1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36}
    if range_key not in months_by_range:
        raise ValueError("Unsupported range")
    cache_key = f"bars:{symbol.upper()}:{range_key}"
    if cached := cache.get(cache_key):
        return cached
    rows = fetch_history(symbol, months_by_range[range_key])
    if range_key == "1D":
        rows = rows[-1:]
    elif range_key == "1W":
        rows = rows[-5:]
    response = {"symbol": symbol.upper(), "range": range_key, "source": "NSE Bhavcopy MCP", "as_of": rows[-1]["date"] if rows else None, "bars": rows}
    cache.set(cache_key, response, 3600)
    return response
