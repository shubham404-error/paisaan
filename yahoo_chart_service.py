"""Deterministic Yahoo Finance daily-chart data and Plotly presentation."""
from __future__ import annotations

import re

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PUBLIC_SYMBOL = re.compile(r"^[A-Z0-9&-]{1,32}$")
OVERLAYS = ("EMA9", "EMA21", "SMA20", "SMA50", "SMA200", "EMA255")
ADJUSTMENT_CONTRACT = "raw-close-plus-adjusted-ohlc-v1"


class YahooChartError(RuntimeError):
    """A controlled provider/data-contract error safe to show in the UI."""


def yahoo_symbol(public_symbol: str) -> str:
    """Map a verified NSE public symbol to Yahoo's NSE symbol without guessing."""
    symbol = public_symbol.strip().upper()
    if symbol == "^NSEI":
        return symbol
    if symbol.endswith(".NS"):
        symbol = symbol[:-3]
    if not PUBLIC_SYMBOL.fullmatch(symbol):
        raise ValueError("Unsupported NSE symbol.")
    return f"{symbol}.NS"


def _single_ticker_frame(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if not isinstance(raw.columns, pd.MultiIndex):
        return raw.copy()
    for level in range(raw.columns.nlevels):
        values = raw.columns.get_level_values(level)
        if symbol in values:
            return raw.xs(symbol, axis=1, level=level, drop_level=True).copy()
    raise YahooChartError("Yahoo Finance returned data for an unexpected symbol.")


def normalize_history(raw: pd.DataFrame | None, symbol: str) -> pd.DataFrame:
    """Validate Yahoo raw data and build adjusted OHLC while retaining RawClose."""
    if raw is None or raw.empty:
        raise YahooChartError("No daily market data is available for this symbol.")
    frame = _single_ticker_frame(raw, symbol)
    required = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise YahooChartError("Yahoo Finance returned incomplete daily OHLCV data.")

    frame = frame.reset_index()
    date_column = "Date" if "Date" in frame.columns else frame.columns[0]
    frame = frame.rename(columns={date_column: "Date"})
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
    for column in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["RawClose"] = frame["Close"]
    raw_close = frame["RawClose"].replace(0, pd.NA)
    frame["AdjustmentFactor"] = frame["Adj Close"] / raw_close
    factor = frame["AdjustmentFactor"]
    for column in ["Open", "High", "Low", "Close"]:
        frame[column] = frame[column] * factor

    valid = (
        frame[["Open", "High", "Low", "Close", "RawClose", "AdjustmentFactor"]].notna().all(axis=1)
        & frame[["Open", "High", "Low", "Close", "RawClose", "AdjustmentFactor"]].gt(0).all(axis=1)
        & frame["Volume"].notna()
        & frame["Volume"].ge(0)
        & frame["High"].ge(frame[["Open", "Close", "Low"]].max(axis=1))
        & frame["Low"].le(frame[["Open", "Close", "High"]].min(axis=1))
    )
    frame = frame.loc[valid, ["Date", "Open", "High", "Low", "Close", "RawClose", "Volume", "AdjustmentFactor"]]
    frame = frame.dropna(subset=["Date"]).drop_duplicates("Date", keep="last").sort_values("Date").reset_index(drop=True)
    if frame.empty:
        raise YahooChartError("Yahoo Finance returned malformed daily OHLCV data.")
    return frame


def download_daily_history(symbol: str, period: str = "3y", interval: str = "1d", adjustment_contract: str = ADJUSTMENT_CONTRACT) -> pd.DataFrame:
    """Download raw Yahoo daily OHLCV and normalize under the explicit contract."""
    if adjustment_contract != ADJUSTMENT_CONTRACT:
        raise ValueError("Unsupported price-adjustment contract.")
    try:
        import yfinance as yf

        raw = yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False, threads=False)
    except Exception as error:
        raise YahooChartError("Yahoo Finance is temporarily unavailable. Try again shortly.") from error
    return normalize_history(raw, symbol)


def load_with_last_valid(loader, last_valid: pd.DataFrame | None = None) -> tuple[pd.DataFrame, bool]:
    """Keep a displayed chart intact when a provider refresh fails."""
    try:
        return loader(), False
    except YahooChartError:
        if last_valid is None or last_valid.empty:
            raise
        return last_valid, True


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    average_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss.replace(0, 1e-12)
    return 100 - 100 / (1 + relative_strength)


def calculate_indicators(history: pd.DataFrame) -> pd.DataFrame:
    """Port of the Terminal daily-chart indicators and crossover definitions."""
    required = {"Date", "High", "Low", "Close", "Volume"}
    missing = required.difference(history.columns)
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {sorted(missing)}")
    frame = history.sort_values("Date").drop_duplicates("Date").copy()
    close = pd.to_numeric(frame["Close"], errors="coerce")
    volume = pd.to_numeric(frame["Volume"], errors="coerce")
    frame["EMA9"] = close.ewm(span=9, adjust=False).mean()
    frame["EMA21"] = close.ewm(span=21, adjust=False).mean()
    frame["SMA20"] = close.rolling(20, min_periods=20).mean()
    frame["SMA50"] = close.rolling(50, min_periods=50).mean()
    frame["SMA200"] = close.rolling(200, min_periods=200).mean()
    frame["EMA255"] = close.ewm(span=255, adjust=False, min_periods=255).mean()
    frame["RSI14"] = rsi_wilder(close, 14)
    frame["VolumeSMA20"] = volume.rolling(20, min_periods=20).mean()
    frame["Cross9_21"] = (frame["EMA9"] > frame["EMA21"]) & (frame["EMA9"].shift(1) <= frame["EMA21"].shift(1))
    frame["Cross20_50"] = (frame["SMA20"] > frame["SMA50"]) & (frame["SMA20"].shift(1) <= frame["SMA50"].shift(1))
    frame["Cross50_200"] = (frame["SMA50"] > frame["SMA200"]) & (frame["SMA50"].shift(1) <= frame["SMA200"].shift(1))
    return frame


def market_chart(
    frame: pd.DataFrame,
    symbol: str,
    overlays: list[str],
    days: int = 180,
    rsi_lines: list[tuple[float, str]] | None = None,
) -> go.Figure:
    """Three-panel Terminal-compatible daily candlestick chart."""
    chart = frame.sort_values("Date").tail(days).copy()
    figure = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.025, row_heights=[0.66, 0.14, 0.20])
    figure.add_trace(go.Candlestick(x=chart["Date"], open=chart["Open"], high=chart["High"], low=chart["Low"], close=chart["Close"], name=symbol, increasing_line_color="#2bd4a4", increasing_fillcolor="#2bd4a4", decreasing_line_color="#ff6b6b", decreasing_fillcolor="#ff6b6b"), row=1, col=1)
    colors = {"EMA9": "#6ea8fe", "EMA21": "#f0a51a", "SMA20": "#b084f5", "SMA50": "#14b8a6", "SMA200": "#ef6461", "EMA255": "#f59e0b"}
    for column in overlays:
        if column in chart.columns and chart[column].notna().any():
            figure.add_trace(go.Scatter(x=chart["Date"], y=chart[column], mode="lines", name=column, line={"width": 1.8, "color": colors.get(column, "#cbd5e1")}), row=1, col=1)
    labels = {"Cross9_21": "9/21 Bullish Cross", "Cross20_50": "20/50 Bullish Cross", "Cross50_200": "Golden Cross"}
    for column, label in labels.items():
        if column not in chart:
            continue
        marks = chart.loc[chart[column].fillna(False)]
        if not marks.empty:
            figure.add_trace(go.Scatter(x=marks["Date"], y=marks["Close"], mode="markers", name=label, marker={"symbol": "triangle-up", "size": 9, "color": "#2bd4a4", "line": {"color": "#080a0d", "width": 1}}), row=1, col=1)
    figure.add_trace(go.Bar(x=chart["Date"], y=chart["Volume"], name="Volume", marker_color="#64748b"), row=2, col=1)
    if "VolumeSMA20" in chart.columns and chart["VolumeSMA20"].notna().any():
        figure.add_trace(go.Scatter(x=chart["Date"], y=chart["VolumeSMA20"], mode="lines", name="20D Avg Vol", line={"width": 1.3, "color": "#f0a51a"}), row=2, col=1)
    if "RSI14" in chart.columns and chart["RSI14"].notna().any():
        figure.add_trace(go.Scatter(x=chart["Date"], y=chart["RSI14"], mode="lines", name="RSI14", line={"width": 1.7, "color": "#8ab4ff"}), row=3, col=1)
    for level, label in rsi_lines or [(30, "RSI 30"), (70, "RSI 70")]:
        figure.add_hline(y=level, row=3, col=1, line_dash="dot", line_color="#46515f", line_width=1, annotation_text=label, annotation_position="top left", annotation_font={"size": 9, "color": "#7f8b99"})
    figure.update_layout(height=690, margin={"l": 8, "r": 8, "t": 40, "b": 10}, paper_bgcolor="#080a0d", plot_bgcolor="#080a0d", font={"family": "Helvetica, Arial, sans-serif", "color": "#e9eef3"}, legend={"orientation": "h", "y": 1.03, "x": 0, "font": {"size": 10}}, hovermode="x unified", xaxis_rangeslider_visible=False, xaxis2_rangeslider_visible=False, xaxis3_rangeslider_visible=False)
    for row in (1, 2, 3):
        figure.update_yaxes(gridcolor="#1d232b", linecolor="#252c35", showline=False, zeroline=False, row=row, col=1)
    figure.update_yaxes(range=[0, 100], title_text="RSI", title_font={"size": 10, "color": "#8c98a6"}, row=3, col=1)
    return figure
