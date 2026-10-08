"""Direct, cache-friendly NSE data functions for the Streamlit-only deployment.

These functions deliberately do not persist data or schedule jobs: Streamlit
Cloud can restart at any time. The app caches their output for the current
runtime and displays the source timestamp to users.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import time
from urllib.request import Request, urlopen

import pandas as pd

from nse_mcp import BHAVCOPY_URL, call_nse_tool

NIFTY_200_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"
RETRY_ATTEMPTS = 3


def _retry(operation, description: str):
    """Retry intermittent exchange failures without hiding a final error."""
    last_error: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"NSE request failed while loading {description}. Please retry shortly.") from last_error


def fetch_constituents() -> list[dict]:
    def download() -> pd.DataFrame:
        request = Request(NIFTY_200_URL, headers={"User-Agent": "paisaan/1.0"})
        with urlopen(request, timeout=20) as response:
            return pd.read_csv(StringIO(response.read().decode("utf-8-sig")))
    frame = _retry(download, "the official Nifty 200 constituent file")
    frame = frame.rename(columns={"Company Name": "company", "Industry": "industry", "Symbol": "symbol", "Series": "series", "ISIN Code": "isin"})
    required = {"symbol", "company", "industry"}
    if not required.issubset(frame.columns) or len(frame) != 200:
        raise RuntimeError("Official Nifty 200 constituent feed did not return the expected 200 symbols.")
    return frame.to_dict("records")


def fetch_quotes(constituents: list[dict]) -> list[dict]:
    """Retrieve quotes only for verified Nifty 200 members, in MCP-safe batches."""
    symbols = [item["symbol"] for item in constituents]
    batches = [symbols[offset:offset + 50] for offset in range(0, len(symbols), 50)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda batch: _retry(lambda: call_nse_tool("get_bulk_quote", {"symbols": batch}, BHAVCOPY_URL), "Nifty 200 quotes"), batches))
    by_symbol = {quote["symbol"]: quote for response in responses for quote in response.get("quotes", [])}
    rows = [{**item, **by_symbol[item["symbol"]]} for item in constituents if item["symbol"] in by_symbol]
    if len(rows) != 200:
        raise RuntimeError(f"NSE Bhavcopy returned {len(rows)} of 200 verified Nifty 200 quotes. Try again shortly.")
    return rows


def fetch_history(symbol: str, months: int) -> list[dict]:
    """Get a single symbol's historical bars. Use only on the chart/detail path."""
    rows, end_date, remaining = [], "today", months
    while remaining > 0:
        chunk = min(3, remaining)
        response = _retry(lambda: call_nse_tool("get_stock_history", {"symbol": symbol.upper(), "months": chunk, "endDate": end_date}, BHAVCOPY_URL), f"{symbol.upper()} history")
        rows.extend(response.get("data", []))
        end_date = response.get("next_end_date")
        if not end_date:
            break
        remaining -= chunk
    return sorted({row["date"]: row for row in rows}.values(), key=lambda row: row["date"])
