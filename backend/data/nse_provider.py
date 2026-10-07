"""Supplier adapter. All NSE MCP traffic is isolated from UI code here."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from urllib.request import Request, urlopen

import pandas as pd

from nse_mcp import BHAVCOPY_URL, call_nse_tool

NIFTY_200_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv"


def fetch_constituents() -> list[dict]:
    request = Request(NIFTY_200_URL, headers={"User-Agent": "paisaan/1.0"})
    with urlopen(request, timeout=20) as response:
        frame = pd.read_csv(StringIO(response.read().decode("utf-8-sig")))
    frame = frame.rename(columns={"Company Name": "company", "Industry": "industry", "Symbol": "symbol", "Series": "series", "ISIN Code": "isin"})
    return frame.to_dict("records")


def fetch_nifty_200_quotes(constituents: list[dict]) -> list[dict]:
    symbols = [item["symbol"] for item in constituents if item.get("symbol")]
    batches = [symbols[index:index + 50] for index in range(0, len(symbols), 50)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda batch: call_nse_tool("get_bulk_quote", {"symbols": batch}, BHAVCOPY_URL), batches))
    by_symbol = {quote["symbol"]: quote for response in responses for quote in response.get("quotes", [])}
    return [{**item, **by_symbol[item["symbol"]]} for item in constituents if item["symbol"] in by_symbol]


def fetch_history(symbol: str, months: int) -> list[dict]:
    rows, end_date, remaining = [], "today", months
    while remaining > 0:
        chunk = min(3, remaining)
        response = call_nse_tool("get_stock_history", {"symbol": symbol.upper(), "months": chunk, "endDate": end_date}, BHAVCOPY_URL)
        rows.extend(response.get("data", []))
        end_date = response.get("next_end_date")
        if not end_date:
            break
        remaining -= chunk
    return sorted({row["date"]: row for row in rows}.values(), key=lambda row: row["date"])
