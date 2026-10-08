"""Pure, chart-local technical calculations used by the Streamlit view."""
from __future__ import annotations

import pandas as pd


def add_technicals(history: pd.DataFrame) -> pd.DataFrame:
    """Add indicators that can be calculated from one selected symbol's bars."""
    result = history.copy()
    close = result["close"].astype(float)
    for window in (20, 50, 200):
        result[f"sma{window}"] = close.rolling(window).mean()
    delta = close.diff()
    average_gain = delta.clip(lower=0).rolling(14).mean()
    average_loss = (-delta.clip(upper=0)).rolling(14).mean()
    relative_strength = average_gain / average_loss.replace(0, float("nan"))
    result["rsi14"] = (100 - (100 / (1 + relative_strength))).mask((average_loss == 0) & (average_gain > 0), 100)
    return result


def technical_summary(history: pd.DataFrame) -> dict[str, float | None]:
    close = history["close"]
    latest = history.iloc[-1]

    def value(column: str) -> float | None:
        item = latest.get(column)
        return None if pd.isna(item) else float(item)

    return {
        "rsi14": value("rsi14"),
        "sma20": value("sma20"),
        "sma50": value("sma50"),
        "sma200": value("sma200"),
        "return_1m": ((close.iloc[-1] / close.iloc[-22]) - 1) * 100 if len(close) >= 22 else None,
    }
