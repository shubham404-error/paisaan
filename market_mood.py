"""Read the public, server-rendered Tickertape Market Mood Index snapshot."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.request import Request, urlopen


TICKERTAPE_MMI_URL = "https://www.tickertape.in/market-mood-index"
NEXT_DATA_PATTERN = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL)


class MarketMoodError(RuntimeError):
    """A controlled public-page extraction error safe to show in the dashboard."""


def _daily_mmi_series(node: Any) -> list[dict] | None:
    """Find Tickertape's server-rendered daily MMI series without relying on internal URLs."""
    if isinstance(node, dict):
        series = node.get("periodicDailyMMI")
        if isinstance(series, list):
            return series
        for value in node.values():
            found = _daily_mmi_series(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _daily_mmi_series(value)
            if found is not None:
                return found
    return None


def fetch_tickertape_mmi() -> dict[str, object]:
    """Return the latest public MMI number and its source timestamp."""
    try:
        request = Request(
            TICKERTAPE_MMI_URL,
            headers={
                "User-Agent": "paisaan research desk/1.0 (+https://github.com/shubham404-error/paisaan)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urlopen(request, timeout=15) as response:
            page = response.read().decode("utf-8", errors="replace")
    except OSError as error:
        raise MarketMoodError("Tickertape could not be reached.") from error

    match = NEXT_DATA_PATTERN.search(page)
    if not match:
        raise MarketMoodError("Tickertape's public MMI snapshot was not found.")
    try:
        series = _daily_mmi_series(json.loads(match.group(1)))
        latest = max(series or [], key=lambda item: str(item.get("date", "")))
        value = float(latest["indicator"])
        as_of = datetime.fromisoformat(str(latest["date"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise MarketMoodError("Tickertape returned an invalid MMI snapshot.") from error
    if not 0 <= value <= 100:
        raise MarketMoodError("Tickertape returned an out-of-range MMI value.")
    return {"value": round(value, 1), "as_of": as_of.strftime("%d %b %Y")}


def mmi_zone(value: float) -> tuple[str, str]:
    """Use Tickertape's public 0–100 fear/greed scale for display only."""
    if value < 30:
        return "Extreme fear", "#35d391"
    if value < 50:
        return "Fear", "#82d8a8"
    if value <= 70:
        return "Greed", "#f0a51a"
    return "Extreme greed", "#ff6b6b"
