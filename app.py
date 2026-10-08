from __future__ import annotations

from html import escape
import json
import os
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from gemini_screener import DEFAULT_MODEL, GeminiScreenerError, ask_chart_question, ask_stock_comparison, build_chart_research_cues, build_research_shortlist, compare_research_stocks, translate_screener_request
from streamlit_data import fetch_constituents, fetch_quotes
from refresh_control import RefreshGate
from screener_service import FIELD_LABELS, fetch_yahoo_fundamentals, filter_fundamentals, parse_fundamental_query
from watchlist_service import WatchlistError, add_to_watchlist, create_watchlist, default_watchlists, encode_shared_watchlist, export_watchlists, import_shared_watchlist, normalize_watchlists, remove_from_watchlist
from yahoo_chart_service import ADJUSTMENT_CONTRACT, OVERLAYS, YahooChartError, calculate_indicators, download_daily_history, load_with_last_valid, market_chart, yahoo_symbol

st.set_page_config(page_title="paisaan · CapitalSense Advisors", page_icon="₹", layout="wide")

ACCENT, GREEN, RED, MUTED = "#2bd4a4", "#2bd4a4", "#ff6b6b", "#8d98a7"
AI_RESEARCH_SCHEMA_VERSION = "v2"
TRENDLYNE_WIDGET_BASE_URL = "https://trendlyne.com/web-widget"


def safe_text(value: object) -> str:
    return escape(str(value))


def trendlyne_widget_url(widget: str, symbol: str) -> str:
    """Build Trendlyne's documented public widget URL for an NSE symbol."""
    if widget not in {"qvt-widget", "swot-widget", "technical-widget"}:
        raise ValueError("Unsupported Trendlyne widget.")
    encoded_symbol = quote(symbol.strip().upper(), safe="")
    palette = urlencode({"posCol": "2BD4A4", "primaryCol": "2BD4A4", "negCol": "FF6B6B", "neuCol": "F0A51A", "theme": "light"})
    return f"{TRENDLYNE_WIDGET_BASE_URL}/{widget}/Poppins/{encoded_symbol}/?{palette}"


def trendlyne_widget(widget: str, symbol: str, height: int) -> None:
    """Render third-party widget in an isolated iframe so provider JS stays outside the app."""
    url = trendlyne_widget_url(widget, symbol)
    if widget == "swot-widget":
        # Trendlyne's SWOT page uses dark text but a transparent page background.
        # A light host canvas keeps its provider content readable inside paisaan's dark UI.
        components.html(
            f"""<style>html,body{{margin:0;background:#f7faf9;overflow:hidden}}iframe{{display:block;width:100%;height:{height}px;border:0;background:#f7faf9}}</style><iframe src=\"{escape(url, quote=True)}\" scrolling=\"yes\" title=\"Trendlyne SWOT\"></iframe>""",
            height=height,
            scrolling=False,
        )
        return
    components.iframe(url, height=height, scrolling=True)


@st.cache_resource
def refresh_gate() -> RefreshGate:
    """Share explicit-refresh protection across users on this app instance."""
    return RefreshGate(cooldown_seconds=60)


def gemini_settings() -> tuple[str, str]:
    """Read optional AI configuration without exposing a key in UI or source control."""
    try:
        api_key = str(st.secrets.get("GEMINI_API_KEY", ""))
        model = str(st.secrets.get("GEMINI_MODEL", DEFAULT_MODEL))
    except FileNotFoundError:
        api_key = os.getenv("GEMINI_API_KEY", "")
        model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    return api_key.strip(), model.strip() or DEFAULT_MODEL


def inject_css():
    st.markdown("""
    <style>
      .stApp { background: radial-gradient(54% 35% at 86% -5%, #174c3a 0%, transparent 55%), radial-gradient(36% 25% at 45% 0%, #20244d 0%, transparent 68%), #070a0e; }
      /* Streamlit's hosted toolbar overlays the top edge on some surfaces.
         Reserve one shared safe area so every page starts below it. */
      .block-container { max-width: 1440px; padding-top: 2.35rem; padding-bottom: 2.5rem; }
      [data-testid="stMainBlockContainer"] { padding-top: 2.35rem !important; }
      [data-testid="stSidebar"] { background: linear-gradient(180deg, #0c1117, #080b10); border-right: 1px solid #222a33; }
      [data-testid="stSidebar"] .block-container { padding-top: 1.2rem !important; }
      .brand { font-size: 1.4rem; font-weight: 750; letter-spacing: -0.06em; }
      .brand b { color: #2bd4a4; }
      .eyebrow { color: #8d98a7; text-transform: uppercase; font-size: .72rem; letter-spacing: .14em; }
      .topbar { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding: .35rem 0 1.2rem; }
      .live-dot { display:inline-block; width:7px; height:7px; border-radius:999px; background:#2bd4a4; box-shadow: 0 0 0 5px rgba(43,212,164,.12); margin-right:.5rem; }
      .market-pill { border:1px solid #23323a; background:rgba(13,23,27,.76); padding:.45rem .75rem; border-radius:999px; color:#b9c3ce; font-size:.78rem; }
      .market-tape { display:flex; align-items:stretch; overflow:hidden; margin:-.3rem 0 1rem; border:1px solid #23343a; border-radius:11px; background:rgba(11,17,22,.78); }
      .market-tape-label { display:flex; align-items:center; flex:0 0 auto; padding:0 .8rem; color:#9eabba; background:#101a20; border-right:1px solid #26353b; font-size:.68rem; font-weight:750; letter-spacing:.12em; text-transform:uppercase; z-index:1; }
      .market-tape-viewport { min-width:0; overflow:hidden; }
      .market-tape-track { display:flex; width:max-content; animation:market-tape-scroll 42s linear infinite; }
      .market-tape-group { display:flex; align-items:center; white-space:nowrap; }
      .market-tape-item { display:inline-flex; align-items:center; gap:.42rem; padding:.58rem .86rem; border-right:1px solid #202d33; color:#dce4eb; font-size:.76rem; }
      .market-tape-symbol { font-weight:750; letter-spacing:.01em; } .market-tape-price { color:#8d98a7; } .market-tape-up { color:#2bd4a4; } .market-tape-down { color:#ff7a7a; }
      .market-tape:hover .market-tape-track { animation-play-state:paused; }
      @keyframes market-tape-scroll { from { transform:translateX(0); } to { transform:translateX(-50%); } }
      @media (prefers-reduced-motion: reduce) { .market-tape-track { animation:none; } }
      .source-note { color:#73808f; font-size:.72rem; margin:.5rem 0 1.1rem; }
      .hero { padding: 2.3rem 2.5rem; border: 1px solid #29423e; border-radius: 22px;
              background: linear-gradient(120deg, rgba(17,31,35,.96), rgba(12,18,26,.82)); box-shadow: 0 18px 50px rgba(0,0,0,.16); }
      .hero h1 { font-size: clamp(2.2rem, 4vw, 4.25rem); letter-spacing: -.065em; line-height: .95; margin: .5rem 0; }
      .glow { color: #2bd4a4; }
      .card { background: rgba(16,22,29,.88); border: 1px solid #242d37; border-radius: 16px; padding: 1rem 1.1rem; min-height: 110px; }
      .metric-label { color: #8d98a7; font-size: .76rem; text-transform: uppercase; letter-spacing: .09em; }
      .metric-value { font-size: 1.55rem; font-weight: 700; margin-top: .28rem; }
      .gain { color: #2bd4a4; } .loss { color: #ff6b6b; }
      div[data-testid="stMetric"] { background: linear-gradient(145deg, rgba(22,30,38,.96), rgba(12,17,23,.96)); border: 1px solid #26313d; padding: 1rem; border-radius: 15px; box-shadow: inset 0 1px rgba(255,255,255,.025); }
      [data-testid="stMetricLabel"] { color:#98a4b3; font-size:.74rem; text-transform:uppercase; letter-spacing:.09em; }
      [data-testid="stMetricValue"] { letter-spacing:-.04em; }
      .panel-title { font-size:1.03rem; font-weight:650; letter-spacing:-.025em; }
      .panel-subtitle { color:#7f8b99; font-size:.78rem; margin-top:.12rem; }
      .feed { background: rgba(255,255,255,.035); border: 1px solid #202932; border-radius: 12px; padding: .85rem .9rem; margin-bottom: .55rem; transition: .15s ease; }
      .feed:hover { background:rgba(43,212,164,.07); border-color:#315448; transform:translateY(-1px); }
      .move-bar { height:5px; border-radius:99px; background:#202a33; overflow:hidden; margin-top:.55rem; }
      .move-fill { height:100%; border-radius:99px; background:linear-gradient(90deg, #2bd4a4, #7cf0ff); }
      .section-title { font-size:1.08rem; font-weight:680; letter-spacing:-.025em; margin:1.4rem 0 .18rem; }
      .section-copy { color:#8390a0; font-size:.8rem; margin:0 0 .75rem; }
      .sector-chip { display:inline-flex; align-items:center; gap:.45rem; padding:.45rem .62rem; margin:0 .35rem .35rem 0; border:1px solid #25313a; background:#10171e; border-radius:10px; font-size:.78rem; }
      .sector-dot { width:7px; height:7px; border-radius:50%; display:inline-block; }
      .sentiment { border-left:3px solid #2bd4a4; background:rgba(43,212,164,.06); border-radius:0 12px 12px 0; padding:.75rem .9rem; margin:1rem 0 .2rem; color:#c8d1da; font-size:.9rem; }
      .meme-note { display:inline-flex; align-items:center; gap:.45rem; margin-top:1rem; padding:.42rem .65rem; border:1px solid rgba(43,212,164,.28); border-radius:999px; background:rgba(43,212,164,.07); color:#c8d1da; font-size:.76rem; }
      .meme-note b { color:#2bd4a4; letter-spacing:.02em; }
      .small-note { color: #8d98a7; font-size: .78rem; }
      .stButton button { border-radius: 999px; border-color: #315448; font-weight:600; }
      .stDataFrame { border:1px solid #242d37; border-radius:14px; overflow:hidden; }
      [data-testid="stRadio"] label { border-radius:9px; }
      [data-testid="stRadio"] { gap: .45rem; }
      [data-testid="stRadio"] label { padding: .15rem .25rem; }
      .chart-heading { font-size:1.55rem; font-weight:700; letter-spacing:-.045em; margin:0 0 .6rem; }
      .chart-meta { color:#8d98a7; font-size:.82rem; margin-top:-.35rem; margin-bottom:.65rem; }
      .chart-hero { padding:1.1rem 1.25rem .9rem; margin-bottom:.9rem; border:1px solid #293a43; border-radius:16px; background:linear-gradient(115deg, rgba(15,27,34,.94), rgba(12,18,26,.88)); }
      .chart-hero h1 { margin:.12rem 0 .25rem; font-size:1.65rem; letter-spacing:-.05em; }
      .chart-guide { display:grid; grid-template-columns:repeat(3, 1fr); gap:.55rem; margin-top:.75rem; }
      .chart-guide-item { padding:.55rem .65rem; border-left:2px solid #2bd4a4; background:rgba(43,212,164,.045); color:#aab7c4; font-size:.74rem; line-height:1.38; }
      .chart-guide-item b { display:block; color:#e9eef3; margin-bottom:.12rem; }
      @media (max-width: 760px) { .chart-guide { grid-template-columns:1fr; } }
      .screener-hero { padding:1.3rem 1.5rem 1.05rem; margin-bottom:1rem; border:1px solid #263b3a; border-radius:18px; background:linear-gradient(115deg, rgba(17,36,35,.92), rgba(14,20,29,.9)); }
      .screener-hero h1 { margin:.15rem 0 .28rem; font-size:2rem; letter-spacing:-.055em; }
      .screener-kicker { color:#2bd4a4; font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; }
      .screener-hero-top { display:flex; align-items:end; justify-content:space-between; gap:1.25rem; }
      .screener-hero-copy { max-width:42rem; }
      .screener-hero-note { max-width:18rem; padding:.65rem .75rem; border-left:2px solid #2bd4a4; color:#aab7c4; font-size:.77rem; line-height:1.45; background:rgba(43,212,164,.055); border-radius:0 9px 9px 0; }
      .guide-steps { display:grid; grid-template-columns:repeat(3, 1fr); gap:.6rem; margin-top:1rem; }
      .guide-step { min-height:72px; padding:.7rem .75rem; border:1px solid #29413f; border-radius:11px; background:rgba(6,12,16,.28); }
      .guide-number { display:inline-flex; align-items:center; justify-content:center; width:19px; height:19px; margin-right:.4rem; border-radius:50%; background:rgba(43,212,164,.14); color:#2bd4a4; font-size:.64rem; font-weight:750; }
      .guide-step b { color:#e9eef3; font-size:.82rem; }
      .guide-step p { margin:.34rem 0 0; color:#8d98a7; font-size:.73rem; line-height:1.38; }
      @media (max-width: 760px) { .screener-hero-top { display:block; } .screener-hero-note { margin-top:.8rem; max-width:none; } .guide-steps { grid-template-columns:1fr; } }
      .scan-summary { padding:.7rem .85rem; border:1px solid #26313d; border-radius:12px; background:rgba(16,22,29,.72); color:#b9c3ce; font-size:.82rem; }
      .scan-summary b { color:#f0f4f8; }
      .watchlist-hero { position:relative; overflow:hidden; padding:1.35rem 1.5rem; margin-bottom:1rem; border:1px solid #2a4842; border-radius:18px; background:linear-gradient(120deg, rgba(14,39,36,.95), rgba(14,21,30,.92)); }
      .watchlist-hero:after { content:""; position:absolute; width:260px; height:260px; right:-100px; top:-150px; border:1px solid rgba(43,212,164,.18); border-radius:50%; box-shadow:0 0 0 35px rgba(43,212,164,.025), 0 0 0 70px rgba(43,212,164,.02); }
      .watchlist-hero-inner { position:relative; z-index:1; display:flex; align-items:center; justify-content:space-between; gap:1rem; }
      .watchlist-hero h1 { margin:.15rem 0 .3rem; font-size:2rem; letter-spacing:-.055em; }
      .watchlist-hero-copy { max-width:42rem; }
      .watchlist-count { display:flex; align-items:baseline; gap:.25rem; min-width:106px; padding:.7rem .85rem; border:1px solid rgba(43,212,164,.25); border-radius:13px; background:rgba(4,15,17,.35); }
      .watchlist-count b { color:#f4f8fb; font-size:1.55rem; letter-spacing:-.06em; }
      .watchlist-count span { color:#83a79f; font-size:.78rem; }
      .watchlist-status { display:flex; align-items:center; flex-wrap:wrap; gap:.45rem .75rem; margin:.15rem 0 1.1rem; padding:.65rem .82rem; border:1px solid #263c3b; border-radius:11px; background:rgba(43,212,164,.045); color:#9daab6; font-size:.78rem; }
      .watchlist-status b { color:#edf4f3; }
      .watchlist-status-dot { width:7px; height:7px; border-radius:50%; background:#2bd4a4; box-shadow:0 0 0 4px rgba(43,212,164,.12); }
      .watchlist-status-badge { padding:.2rem .45rem; border-radius:999px; background:rgba(43,212,164,.12); color:#65e6bd; font-size:.68rem; font-weight:700; }
      .watchlist-section-head { display:flex; align-items:end; justify-content:space-between; gap:1rem; margin:1.25rem 0 .55rem; }
      .watchlist-section-head h2 { margin:0; font-size:1.08rem; letter-spacing:-.025em; }
      .watchlist-section-head p { margin:.16rem 0 0; color:#84919f; font-size:.77rem; }
      .watchlist-empty { padding:1.15rem 1.2rem; border:1px dashed #315048; border-radius:14px; background:rgba(43,212,164,.035); }
      .watchlist-empty b { display:block; margin-bottom:.18rem; color:#eaf2f1; font-size:1rem; }
      @media (max-width: 760px) { .watchlist-hero-inner { display:block; } .watchlist-count { display:inline-flex; margin-top:.85rem; } .watchlist-section-head { display:block; } }
      </style>
    """, unsafe_allow_html=True)


@st.cache_data(ttl=600, show_spinner="Loading official Nifty 200 data from NSE MCP…")
def live_universe() -> tuple[pd.DataFrame, str]:
    """Load verified Nifty 200 quotes directly; no API service is required."""
    rows = fetch_quotes(fetch_constituents())
    frame = pd.DataFrame(rows).rename(columns={"symbol": "Symbol", "company": "Company", "industry": "Industry", "close": "Price", "pct_change": "Change %", "volume": "Volume", "high": "Day High", "low": "Day Low", "prev_close": "Previous Close"})
    if frame.empty:
        raise RuntimeError("NSE returned no Nifty 200 rows.")
    return frame, str(frame["date"].iloc[0])


def sector_snapshot(data: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    """Compute sector breadth from the cached EOD quote snapshot."""
    groups = data.groupby("Industry", dropna=False)
    rows = [{"industry": industry or "Unclassified", "members": len(group), "advancers": int((group["Change %"] > 0).sum()), "decliners": int((group["Change %"] < 0).sum()), "average_change_pct": group["Change %"].mean(), "turnover": float((group["Price"] * group["Volume"]).sum())} for industry, group in groups]
    return pd.DataFrame(rows).sort_values("average_change_pct", ascending=False), str(data["date"].iloc[0])


def screened_stocks(
    data: pd.DataFrame,
    industry: str | None,
    query: str,
    min_change: float | None,
    max_change: float | None,
    min_price: float | None,
    max_price: float | None,
    min_day_range_position: float | None,
) -> pd.DataFrame:
    """Filter only verified, cached EOD fields available in this deployment."""
    result = data.copy()
    day_range = (result["Day High"] - result["Day Low"]).replace(0, pd.NA)
    result["Day range %"] = (((result["Price"] - result["Day Low"]) / day_range) * 100).fillna(50).clip(0, 100)
    if industry:
        result = result[result["Industry"] == industry]
    if query.strip():
        needle = query.strip()
        matches = result["Symbol"].str.contains(needle, case=False, regex=False, na=False)
        matches |= result["Company"].str.contains(needle, case=False, regex=False, na=False)
        result = result[matches]
    if min_change is not None:
        result = result[result["Change %"] >= min_change]
    if max_change is not None:
        result = result[result["Change %"] <= max_change]
    if min_price is not None:
        result = result[result["Price"] >= min_price]
    if max_price is not None:
        result = result[result["Price"] <= max_price]
    if min_day_range_position is not None:
        result = result[result["Day range %"] >= min_day_range_position]
    return result


YAHOO_WINDOWS = {"1D": 1, "1W": 5, "1M": 22, "3M": 66, "6M": 132, "1Y": 264, "3Y": 756}


@st.cache_data(ttl=4 * 60 * 60, show_spinner="Loading daily Yahoo Finance chart data…")
def yahoo_chart_history(symbol: str, period: str, interval: str, adjustment_contract: str) -> pd.DataFrame:
    """Cached selected-symbol chart history; cache key includes provider contract."""
    return calculate_indicators(download_daily_history(symbol, period, interval, adjustment_contract))


@st.cache_data(ttl=6 * 60 * 60, show_spinner="Loading Yahoo Finance fundamentals for the shortlist...")
def yahoo_fundamentals(symbols: tuple[str, ...]) -> pd.DataFrame:
    """Cache bounded Yahoo fundamental lookups to keep the screener responsive."""
    return fetch_yahoo_fundamentals(symbols)


@st.cache_data(ttl=4 * 60 * 60, show_spinner="Loading Yahoo Finance comparison data...")
def yahoo_comparison_facts(symbols: tuple[str, ...]) -> dict:
    """Build a Yahoo-only fact packet for an explicitly selected comparison set."""
    fundamentals = yahoo_fundamentals(symbols).set_index("Symbol")
    rows: list[dict] = []
    for public_symbol in symbols:
        history = yahoo_chart_history(yahoo_symbol(public_symbol), "1y", "1d", ADJUSTMENT_CONTRACT)
        latest = history.iloc[-1]
        row = {
            "symbol": public_symbol,
            "as_of": latest["Date"].strftime("%Y-%m-%d"),
            "close": latest["Close"],
            "rsi_14": latest["RSI14"],
            "ema_9": latest["EMA9"],
            "ema_21": latest["EMA21"],
            "sma_50": latest["SMA50"],
            "sma_200": latest["SMA200"],
            "volume_vs_20d_average": (latest["Volume"] / latest["VolumeSMA20"]) if pd.notna(latest["VolumeSMA20"]) and latest["VolumeSMA20"] else None,
        }
        if public_symbol in fundamentals.index:
            row.update(fundamentals.loc[public_symbol, ["pe", "pb", "roe", "dividend_yield", "market_cap_cr"]].to_dict())
        rows.append(row)
    return {"source": "Yahoo Finance daily EOD data", "stocks": json.loads(pd.DataFrame(rows).to_json(orient="records", date_format="iso"))}


@st.cache_data(ttl=4 * 60 * 60, show_spinner="Loading one-year relative returns...")
def yahoo_relative_returns(symbols: tuple[str, ...]) -> pd.DataFrame:
    """Normalize selected stocks and Nifty 50 to a common 0% return start date."""
    close_series: dict[str, pd.Series] = {}
    for public_symbol in symbols:
        history = yahoo_chart_history(yahoo_symbol(public_symbol), "1y", "1d", ADJUSTMENT_CONTRACT)
        close_series[public_symbol] = history.set_index("Date")["Close"]
    benchmark = yahoo_chart_history("^NSEI", "1y", "1d", ADJUSTMENT_CONTRACT)
    close_series["Nifty 50"] = benchmark.set_index("Date")["Close"]
    aligned = pd.concat(close_series, axis=1).sort_index().ffill().dropna()
    if aligned.empty:
        raise YahooChartError("Yahoo Finance could not align return history for this comparison.")
    normalized = aligned.divide(aligned.iloc[0]).subtract(1).multiply(100)
    normalized.index.name = "Date"
    return normalized.reset_index()


def relative_returns_chart(frame: pd.DataFrame, symbols: tuple[str, ...]) -> go.Figure:
    """Show candidate return paths against Nifty 50 from the exact same base date."""
    figure = go.Figure()
    colors = ["#2bd4a4", "#8ab4ff", "#f0a51a", "#b084f5", "#ff6b6b"]
    for index, symbol in enumerate(symbols):
        figure.add_trace(go.Scatter(x=frame["Date"], y=frame[symbol], mode="lines", name=symbol, line={"width": 2, "color": colors[index % len(colors)]}))
    figure.add_trace(go.Scatter(x=frame["Date"], y=frame["Nifty 50"], mode="lines", name="Nifty 50 benchmark", line={"width": 2.2, "dash": "dot", "color": "#e9eef3"}))
    figure.add_hline(y=0, line_color="#46515f", line_width=1)
    figure.update_layout(height=360, margin={"l": 8, "r": 8, "t": 35, "b": 8}, paper_bgcolor="#080a0d", plot_bgcolor="#080a0d", font={"family": "Helvetica, Arial, sans-serif", "color": "#e9eef3"}, legend={"orientation": "h", "y": 1.08, "x": 0, "font": {"size": 10}}, hovermode="x unified")
    figure.update_yaxes(title_text="Return (%)", gridcolor="#1d232b", zeroline=False)
    figure.update_xaxes(gridcolor="#1d232b", zeroline=False)
    return figure


@st.cache_data(ttl=4 * 60 * 60, show_spinner="Loading Yahoo Finance watchlist overview...")
def yahoo_watchlist_overview(symbols: tuple[str, ...]) -> pd.DataFrame:
    """Combine Yahoo fundamentals with comparable 1D/1M/3M/1Y EOD returns."""
    fundamentals = yahoo_fundamentals(symbols).set_index("Symbol")
    rows: list[dict] = []
    for public_symbol in symbols:
        history = yahoo_chart_history(yahoo_symbol(public_symbol), "1y", "1d", ADJUSTMENT_CONTRACT).reset_index(drop=True)
        latest = history.iloc[-1]
        close = history["Close"]
        def trailing_return(days: int) -> float | None:
            if len(close) <= days:
                return None
            return (close.iloc[-1] / close.iloc[-days - 1] - 1) * 100
        row = {"Symbol": public_symbol, "Close": latest["Close"], "1D %": trailing_return(1), "1M %": trailing_return(22), "3M %": trailing_return(66), "1Y %": trailing_return(252), "RSI-14": latest["RSI14"]}
        if public_symbol in fundamentals.index:
            row.update(fundamentals.loc[public_symbol, ["pe", "pb", "roe", "dividend_yield", "market_cap_cr"]].to_dict())
        rows.append(row)
    return pd.DataFrame(rows)


def watchlist_state(valid_symbols: set[str]) -> dict:
    """Keep portable watchlists in Streamlit session only until the user exports or imports them."""
    stored = st.session_state.get("watchlists", default_watchlists())
    try:
        state = normalize_watchlists(stored, valid_symbols)
    except WatchlistError:
        state = default_watchlists()
    st.session_state["watchlists"] = state
    return state


def watchlist_share_url(payload: str) -> str:
    """Return a complete link on hosted Streamlit, with a relative fallback for local runtimes."""
    base_url = ""
    try:
        context_url = str(st.context.url)
        parsed = urlsplit(context_url)
        if parsed.scheme and parsed.netloc:
            base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except (AttributeError, RuntimeError):
        pass
    if not base_url:
        try:
            headers = {str(key).lower(): str(value) for key, value in st.context.headers.items()}
            host = headers.get("x-forwarded-host") or headers.get("host", "")
            protocol = headers.get("x-forwarded-proto", "https")
            if host:
                base_url = f"{protocol}://{host}/"
        except (AttributeError, RuntimeError):
            pass
    query = urlencode({"page": "Watchlists", "watchlist": payload})
    return f"{base_url}?{query}" if base_url else f"?{query}"


def import_shared_watchlist_from_url(valid_symbols: set[str]) -> None:
    """Consume a shared snapshot once, then clean the URL to avoid duplicate imports."""
    payload = st.query_params.get("watchlist")
    if not payload:
        return
    try:
        state = watchlist_state(valid_symbols)
        imported = import_shared_watchlist(state, payload, valid_symbols)
        st.session_state["watchlists"] = imported
        st.session_state["page"] = "Watchlists"
        st.session_state["watchlist-share-notice"] = f"Added {imported['active']} as your editable local copy."
    except WatchlistError as error:
        st.session_state["watchlist-share-error"] = str(error)
    finally:
        del st.query_params["watchlist"]


def watchlist_add_control(symbols: list[str], valid_symbols: set[str], key: str) -> None:
    """Small popover used beside tables and dashboard selectors."""
    state = watchlist_state(valid_symbols)
    with st.popover("＋", help="Add to a watchlist"):
        target = st.selectbox("Watchlist", list(state["lists"]), key=f"watch-target:{key}")
        if st.button(f"Add {len(symbols)} stock(s)", key=f"watch-add:{key}", use_container_width=True):
            try:
                st.session_state["watchlists"] = add_to_watchlist(state, target, symbols, valid_symbols)
                st.success(f"Added to {target}.")
            except WatchlistError as error:
                st.warning(str(error))


def gain(value: float) -> str:
    return f"<span class='{ 'gain' if value >= 0 else 'loss' }'>{value:+.2f}%</span>"


def json_records(frame: pd.DataFrame, columns: list[str], limit: int = 25) -> list[dict]:
    """Create a JSON-safe, bounded fact packet for an optional AI request."""
    available = [column for column in columns if column in frame.columns]
    return json.loads(frame.loc[:, available].head(limit).to_json(orient="records", date_format="iso"))


def open_chart_for(symbol: str) -> None:
    st.session_state["page"] = "Charts"
    st.session_state["chart_symbol"] = symbol


def render_research_list(title: str, items: list[str]) -> None:
    st.markdown(f"**{title}**")
    for item in items:
        st.markdown(f"- {safe_text(item)}")


def screener_research_packet(result: pd.DataFrame, as_of: str, preset: str, rank_by: str) -> dict:
    fields = ["Symbol", "Company", "Industry", "Price", "Change %", "Day range %", "pe", "pb", "roe", "dividend_yield", "market_cap_cr"]
    return {
        "source": "NSE Bhavcopy EOD; optional Yahoo Finance fundamentals",
        "as_of": as_of,
        "screen": {"preset": preset, "ranked_by": rank_by, "match_count": len(result)},
        "ranked_results": json_records(result, fields),
    }


def render_comparison(comparison: dict, selected: pd.DataFrame) -> None:
    required = {"decision_lenses", "data_gaps", "research_actions"}
    if not required.issubset(comparison):
        st.info("This research comparison used an older format. Run the comparison again to refresh it.")
        return
    overview_columns = [column for column in ("Symbol", "Company", "Industry", "Price", "Change %", "Day range %", "pe", "pb", "roe", "dividend_yield", "market_cap_cr") if column in selected]
    st.markdown("**At a glance**")
    st.dataframe(selected[overview_columns], use_container_width=True, hide_index=True, column_config={
        "Price": st.column_config.NumberColumn("Last price", format="Rs %.2f"),
        "Change %": st.column_config.NumberColumn("Day move", format="%+.2f%%"),
        "Day range %": st.column_config.ProgressColumn("Close in day range", format="%.0f%%", min_value=0, max_value=100),
        "pe": st.column_config.NumberColumn("P/E", format="%.1f"),
        "pb": st.column_config.NumberColumn("P/B", format="%.1f"),
        "roe": st.column_config.NumberColumn("ROE", format="%.1f%%"),
        "dividend_yield": st.column_config.NumberColumn("Yield", format="%.1f%%"),
        "market_cap_cr": st.column_config.NumberColumn("Mkt cap", format="Rs %.0f Cr"),
    })
    st.markdown("**Decision lenses**")
    for lens in comparison["decision_lenses"]:
        st.markdown(f"- **{safe_text(lens['dimension'].title())}** ({', '.join(map(safe_text, lens['symbols']))}): {safe_text(lens['takeaway'])}")
    render_research_list("Data gaps to resolve", comparison["data_gaps"])
    st.markdown("**Next research steps**")
    for item in comparison["research_actions"]:
        st.markdown(f"- **{safe_text(item['symbol'])} · {safe_text(item['focus'].title())}:** {safe_text(item['question'])} — {safe_text(item['reason'])}")


def research_workbench(result: pd.DataFrame, as_of: str, preset: str, rank_by: str) -> None:
    """Optional, session-only research actions for an already-populated screen."""
    with st.expander("Build research plan", expanded=False):
        api_key, gemini_model = gemini_settings()
        if not api_key:
            st.info("Add GEMINI_API_KEY in Streamlit secrets to enable the optional research workbench.")
            return
        facts = screener_research_packet(result, as_of, preset, rank_by)
        context_id = str(abs(hash((AI_RESEARCH_SCHEMA_VERSION, as_of, preset, rank_by, tuple(item["Symbol"] for item in facts["ranked_results"])))))
        shortlist_tab, compare_tab = st.tabs(["AI shortlist", "Compare selected"])
        with shortlist_tab:
            st.caption("Creates up to three research candidates from the displayed ranked results. It does not make investment recommendations.")
            shortlist_key = f"research-shortlist:{context_id}"
            if st.button("Build AI shortlist", key=f"build-shortlist:{context_id}"):
                try:
                    st.session_state[shortlist_key] = build_research_shortlist(facts, {item["Symbol"] for item in facts["ranked_results"]}, api_key, gemini_model)
                except GeminiScreenerError as error:
                    st.warning(str(error))
            shortlist = st.session_state.get(shortlist_key)
            if shortlist:
                checked_symbols: list[str] = []
                for candidate in shortlist["candidates"]:
                    st.markdown(f"**{safe_text(candidate['symbol'])}** — {safe_text(candidate['screen_evidence'])}")
                    st.caption(f"Counterpoint: {candidate['counterpoint']}  |  Next step: {candidate['next_step']}")
                    choice_col, chart_col = st.columns([3, 1])
                    if choice_col.checkbox(f"Add {candidate['symbol']} to comparison", key=f"shortlist-choice:{context_id}:{candidate['symbol']}"):
                        checked_symbols.append(candidate["symbol"])
                    chart_col.button("Open chart", key=f"shortlist-chart:{context_id}:{candidate['symbol']}", on_click=open_chart_for, args=(candidate["symbol"],), use_container_width=True)
                if len(checked_symbols) >= 2:
                    if st.button("Compare checked candidates", key=f"compare-shortlist:{context_id}"):
                        selected_facts = dict(facts, selected_stocks=json_records(result[result["Symbol"].isin(checked_symbols)], list(result.columns), limit=5))
                        try:
                            st.session_state[f"research-comparison:{context_id}:shortlist"] = compare_research_stocks(selected_facts, set(checked_symbols), api_key, gemini_model)
                        except GeminiScreenerError as error:
                            st.warning(str(error))
                    comparison = st.session_state.get(f"research-comparison:{context_id}:shortlist")
                    if comparison:
                        render_comparison(comparison, result[result["Symbol"].isin(checked_symbols)])
                elif shortlist:
                    st.caption("Check at least two candidates to compare them.")
        with compare_tab:
            selected_symbols = st.multiselect("Choose 2 to 5 screen results", result["Symbol"].tolist(), max_selections=5, key=f"manual-compare:{context_id}")
            if selected_symbols and len(selected_symbols) < 2:
                st.caption("Choose one more company to compare.")
            if len(selected_symbols) >= 2:
                comparison_key = f"research-comparison:{context_id}:manual:{','.join(sorted(selected_symbols))}"
                if st.button("Compare selected stocks", key=f"run-manual-compare:{context_id}"):
                    selected_facts = dict(facts, selected_stocks=json_records(result[result["Symbol"].isin(selected_symbols)], list(result.columns), limit=5))
                    try:
                        st.session_state[comparison_key] = compare_research_stocks(selected_facts, set(selected_symbols), api_key, gemini_model)
                    except GeminiScreenerError as error:
                        st.warning(str(error))
                comparison = st.session_state.get(comparison_key)
                if comparison:
                    render_comparison(comparison, result[result["Symbol"].isin(selected_symbols)])


def chart_research_cues(history: pd.DataFrame, symbol: str, range_label: str) -> None:
    """Optional technical-context checks for the chart already on screen."""
    with st.expander("Research cues", expanded=False):
        api_key, gemini_model = gemini_settings()
        if not api_key:
            st.info("Add GEMINI_API_KEY in Streamlit secrets to enable optional chart research cues.")
            return
        latest_fields = ["Date", "Close", "RawClose", "Volume", "VolumeSMA20", "RSI14", "EMA9", "EMA21", "SMA20", "SMA50", "SMA200", "EMA255", "Cross9_21", "Cross20_50", "Cross50_200"]
        latest = json_records(history.tail(1), latest_fields, limit=1)[0]
        recent_crosses = json_records(history.loc[history[["Cross9_21", "Cross20_50", "Cross50_200"]].any(axis=1)].tail(5), ["Date", "Cross9_21", "Cross20_50", "Cross50_200"], limit=5)
        facts = {
            "source": "Yahoo Finance daily EOD adjusted OHLC",
            "symbol": symbol,
            "range": range_label,
            "latest": latest,
            "recent_crossover_flags": recent_crosses,
        }
        cue_key = f"chart-cues:{symbol}:{range_label}:{latest.get('Date')}"
        if st.button("Build research cues", key=f"build-{cue_key}"):
            try:
                st.session_state[cue_key] = build_chart_research_cues(facts, api_key, gemini_model)
            except GeminiScreenerError as error:
                st.warning(str(error))
        cues = st.session_state.get(cue_key)
        if cues:
            render_research_list("Observations", cues["observations"])
            if cues["confirmation_checks"]:
                render_research_list("Confirmation checks", cues["confirmation_checks"])
            if cues["limitations"]:
                render_research_list("Limitations", cues["limitations"])


def chart_question_chat(history: pd.DataFrame, symbol: str, range_label: str) -> None:
    """Optional, user-led chart questions instead of automatic indicator narration."""
    with st.expander("Ask this chart", expanded=False):
        api_key, gemini_model = gemini_settings()
        if not api_key:
            st.info("Add GEMINI_API_KEY in Streamlit secrets to ask chart questions.")
            return
        fields = ["Date", "Close", "RawClose", "Volume", "VolumeSMA20", "RSI14", "EMA9", "EMA21", "SMA20", "SMA50", "SMA200", "EMA255", "Cross9_21", "Cross20_50", "Cross50_200"]
        latest = json_records(history.tail(1), fields, limit=1)[0]
        recent_crosses = json_records(history.loc[history[["Cross9_21", "Cross20_50", "Cross50_200"]].any(axis=1)].tail(5), ["Date", "Cross9_21", "Cross20_50", "Cross50_200"], limit=5)
        chart_facts = {"source": "Yahoo Finance daily EOD adjusted OHLC", "symbol": symbol, "range": range_label, "latest": latest, "recent_crossover_flags": recent_crosses}
        chat_key = f"chart-question-chat:v1:{symbol}:{range_label}:{latest.get('Date')}"
        for message in st.session_state.get(chat_key, []):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        st.markdown("**Quick questions**")
        prompt_options = [
            ("Trend", "What is the current trend structure, and what is the one chart condition I should verify next?"),
            ("Momentum", "Does the current momentum setup look supported by the available RSI and moving-average relationships?"),
            ("Key levels", "Which moving-average relationships matter most for this chart setup, and why?"),
            ("Setup change", "What chart development would materially change the current setup?"),
        ]
        prompt_columns = st.columns(2)
        selected_prompt = None
        for index, (label, prompt) in enumerate(prompt_options):
            if prompt_columns[index % 2].button(label, key=f"chart-quick:{chat_key}:{index}", use_container_width=True):
                selected_prompt = prompt
        input_label = "Ask a follow-up about this chart" if st.session_state.get(chat_key) else "Ask about this chart"
        question = selected_prompt or st.chat_input(input_label, key=f"chart-ask:{chat_key}")
        if question:
            messages = st.session_state.setdefault(chat_key, [])
            messages.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("Reading the selected chart..."):
                    try:
                        answer = ask_chart_question(question, chart_facts, messages[:-1], api_key, gemini_model)
                    except GeminiScreenerError as error:
                        st.warning(str(error))
                        return
                st.markdown(answer)
            messages.append({"role": "assistant", "content": answer})


def research_workbench(result: pd.DataFrame, as_of: str, preset: str, rank_by: str) -> None:
    """Open a Yahoo-only, session-scoped comparison chat for user-selected stocks."""
    with st.expander("Compare stocks with AI", expanded=False):
        api_key, gemini_model = gemini_settings()
        if not api_key:
            st.info("Add GEMINI_API_KEY in Streamlit secrets to enable stock comparison chat.")
            return
        selected_symbols = st.multiselect("Choose 2 to 5 stocks", result["Symbol"].tolist(), max_selections=5, key="comparison-chat-symbols")
        if selected_symbols and len(selected_symbols) < 2:
            st.caption("Choose at least two stocks to begin a comparison.")
            return
        if len(selected_symbols) < 2:
            return
        symbols = tuple(sorted(selected_symbols))
        chat_key = f"yahoo-comparison-chat:v1:{','.join(symbols)}"
        if st.button("Start comparison chat", key=f"start-{chat_key}"):
            try:
                st.session_state[chat_key] = {"facts": yahoo_comparison_facts(symbols), "messages": []}
            except (YahooChartError, ValueError) as error:
                st.warning(f"Yahoo Finance comparison data is temporarily unavailable: {error}")
                return
        chat = st.session_state.get(chat_key)
        if chat is None:
            st.caption("Loads Yahoo Finance fundamentals and daily technical snapshots only for the stocks you chose.")
            return
        st.caption(f"Yahoo Finance data loaded for {', '.join(symbols)}. Ask what matters to your decision.")
        comparison_table = pd.DataFrame(chat["facts"]["stocks"]).rename(columns={
            "symbol": "Symbol", "as_of": "As of", "close": "Close", "pe": "P/E", "pb": "P/B", "roe": "ROE %",
            "dividend_yield": "Yield %", "market_cap_cr": "Mkt cap (Cr)", "rsi_14": "RSI-14", "ema_9": "EMA-9",
            "ema_21": "EMA-21", "sma_50": "SMA-50", "sma_200": "SMA-200", "volume_vs_20d_average": "Vol / 20D avg",
        })
        table_columns = ["Symbol", "As of", "Close", "P/E", "P/B", "ROE %", "Yield %", "Mkt cap (Cr)", "RSI-14", "EMA-9", "EMA-21", "SMA-50", "SMA-200"]
        st.markdown("**Yahoo Finance comparison snapshot**")
        st.dataframe(
            comparison_table[[column for column in table_columns if column in comparison_table]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Close": st.column_config.NumberColumn(format="Rs %.2f"),
                "P/E": st.column_config.NumberColumn(format="%.1f"),
                "P/B": st.column_config.NumberColumn(format="%.1f"),
                "ROE %": st.column_config.NumberColumn(format="%.1f%%"),
                "Yield %": st.column_config.NumberColumn(format="%.1f%%"),
                "Mkt cap (Cr)": st.column_config.NumberColumn(format="Rs %.0f Cr"),
                "RSI-14": st.column_config.NumberColumn(format="%.1f"),
                "EMA-9": st.column_config.NumberColumn(format="Rs %.2f"),
                "EMA-21": st.column_config.NumberColumn(format="Rs %.2f"),
                "SMA-50": st.column_config.NumberColumn(format="Rs %.2f"),
                "SMA-200": st.column_config.NumberColumn(format="Rs %.2f"),
            },
        )
        chart_toggle_col, chart_symbol_col = st.columns([1, 2], vertical_alignment="bottom")
        show_chart = chart_toggle_col.toggle("Show 1Y chart", value=True, key=f"show-comparison-chart:{chat_key}")
        chart_symbol = chart_symbol_col.selectbox("Chart symbol", symbols, key=f"comparison-chart-symbol:{chat_key}")
        if show_chart:
            try:
                chart_history, chart_stale = load_with_last_valid(
                    lambda: yahoo_chart_history(yahoo_symbol(chart_symbol), "1y", "1d", ADJUSTMENT_CONTRACT),
                    st.session_state.get(f"comparison-chart-history:{chart_key if False else chat_key}:{chart_symbol}"),
                )
                st.session_state[f"comparison-chart-history:{chat_key}:{chart_symbol}"] = chart_history
                st.plotly_chart(
                    market_chart(chart_history, yahoo_symbol(chart_symbol), ["EMA9", "EMA21", "SMA50", "SMA200"], days=YAHOO_WINDOWS["1Y"], height=520),
                    use_container_width=True,
                    config={"displaylogo": False, "scrollZoom": True},
                )
                if chart_stale:
                    st.caption("Showing the last valid Yahoo Finance chart from this session.")
            except (YahooChartError, ValueError):
                st.warning("This 1-year Yahoo Finance chart is temporarily unavailable.")
        show_relative_returns = st.toggle("Compare 1Y returns vs Nifty 50", value=False, key=f"show-relative-returns:{chat_key}")
        if show_relative_returns:
            try:
                returns = yahoo_relative_returns(symbols)
                st.plotly_chart(relative_returns_chart(returns, symbols), use_container_width=True, config={"displaylogo": False, "scrollZoom": True})
                st.caption("Normalized total price return from the first common Yahoo Finance daily observation. Nifty 50 is the benchmark.")
            except (YahooChartError, ValueError):
                st.warning("The benchmarked return chart is temporarily unavailable.")
        for message in chat["messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        st.markdown("**Quick questions**")
        quick_prompts = [
            ("Valuation", "Which selected stock has the more attractive valuation profile based on the available Yahoo Finance data?"),
            ("Quality", "How do these stocks compare on the available quality signals such as ROE, and what should I inspect next?"),
            ("Technical setup", "Which selected stock has the stronger current technical setup based on price, RSI, and moving averages?"),
            ("Decision checklist", "Give me the three most important checks to make before choosing one of these stocks."),
        ]
        prompt_columns = st.columns(2)
        selected_prompt = None
        for index, (label, prompt) in enumerate(quick_prompts):
            if prompt_columns[index % 2].button(label, key=f"quick-prompt:{chat_key}:{index}", use_container_width=True):
                selected_prompt = prompt
        input_label = "Ask a follow-up about these stocks" if chat["messages"] else "Ask about these selected stocks"
        question = selected_prompt or st.chat_input(input_label, key=f"ask-{chat_key}")
        if question:
            chat["messages"].append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("Comparing the selected Yahoo Finance data..."):
                    try:
                        answer = ask_stock_comparison(question, chat["facts"], chat["messages"][:-1], api_key, gemini_model)
                    except GeminiScreenerError as error:
                        st.warning(str(error))
                        return
                st.markdown(answer)
            chat["messages"].append({"role": "assistant", "content": answer})


def mover_row(row: pd.Series) -> None:
    strength = min(abs(row["Change %"]) / 8 * 100, 100)
    color = GREEN if row["Change %"] >= 0 else RED
    st.markdown(f"<div class='feed'><b>{safe_text(row['Symbol'])}</b><span style='float:right'>{gain(row['Change %'])}</span><br><span class='small-note'>{safe_text(row['Company'])} · ₹{row['Price']:,.2f}</span><div class='move-bar'><div class='move-fill' style='width:{strength:.0f}%;background:{color}'></div></div></div>", unsafe_allow_html=True)


def market_tape(data: pd.DataFrame) -> None:
    """Render a compact, decorative tape from the current verified EOD snapshot."""
    movers = pd.concat([data.nlargest(5, "Change %"), data.nsmallest(5, "Change %")]).drop_duplicates("Symbol")
    items = "".join(
        f"<span class='market-tape-item'><span class='market-tape-symbol'>{safe_text(row.Symbol)}</span><span class='market-tape-price'>₹{row.Price:,.2f}</span><span class='market-tape-{'up' if row['Change %'] >= 0 else 'down'}'>{row['Change %']:+.2f}%</span></span>"
        for _, row in movers.iterrows()
    )
    st.markdown(f"<div class='market-tape'><div class='market-tape-label'>Nifty 200 tape</div><div class='market-tape-viewport'><div class='market-tape-track'><div class='market-tape-group'>{items}</div><div class='market-tape-group' aria-hidden='true'>{items}</div></div></div></div>", unsafe_allow_html=True)


def watchlist_page(data: pd.DataFrame) -> None:
    """Portable, no-login watchlists with opt-in Yahoo overview."""
    valid_symbols = set(data["Symbol"])
    state = watchlist_state(valid_symbols)
    initial_count = len(state["lists"][state["active"]])
    st.markdown(f"""<section class='watchlist-hero'><div class='watchlist-hero-inner'>
      <div class='watchlist-hero-copy'><div class='screener-kicker'>Session watchlists · portable by design</div><h1>Your research shelf.</h1><div class='small-note'>Keep the names worth revisiting, compare their progress, and take the list with you when you leave.</div></div>
      <div class='watchlist-count'><b>{initial_count}</b><span>of 20<br>stocks</span></div>
    </div></section>""", unsafe_allow_html=True)
    list_col, share_col, create_col, sync_col = st.columns([2.1, 1.1, 1, 1], vertical_alignment="bottom")
    active = list_col.selectbox("Active watchlist", list(state["lists"]), index=list(state["lists"]).index(state["active"]), key="active-watchlist")
    if active != state["active"]:
        state["active"] = active
        st.session_state["watchlists"] = state
    with share_col:
        st.caption("Send a copy")
        with st.popover("Share active list", use_container_width=True):
            shared_symbols = state["lists"][state["active"]]
            if not shared_symbols:
                st.info("Add at least one stock before sharing this list.")
            else:
                share_payload = encode_shared_watchlist(state["active"], shared_symbols)
                st.code(watchlist_share_url(share_payload), language=None)
                st.caption("Use the copy icon above. Anyone opening this snapshot receives an editable copy; their edits never change yours.")
    with create_col:
        st.caption("Manage lists")
        with st.popover("New list", use_container_width=True):
            new_name = st.text_input("Name", placeholder="e.g. Banks to study", key="new-watchlist-name")
            if st.button("Create list", key="create-watchlist", use_container_width=True):
                try:
                    st.session_state["watchlists"] = create_watchlist(state, new_name)
                    st.rerun()
                except WatchlistError as error:
                    st.warning(str(error))
    with sync_col:
        st.caption("Keep a copy")
        with st.popover("Save / restore", use_container_width=True):
            st.download_button("Download watchlists", data=json.dumps(export_watchlists(state), indent=2), file_name="paisaan-watchlists.json", mime="application/json", use_container_width=True)
            uploaded = st.file_uploader("Upload a prior watchlist", type="json", key="watchlist-upload")
            if uploaded is not None:
                try:
                    st.session_state["watchlists"] = normalize_watchlists(json.loads(uploaded.getvalue().decode("utf-8")), valid_symbols)
                    st.success("Watchlists restored for this session.")
                except (UnicodeDecodeError, json.JSONDecodeError, WatchlistError):
                    st.warning("That file is not a valid paisaan watchlist export.")
            st.caption("Download/upload is a full offline backup. Share active list creates a single-list snapshot link.")

    state = watchlist_state(valid_symbols)
    symbols = state["lists"][state["active"]]
    if notice := st.session_state.pop("watchlist-share-notice", None):
        st.success(notice)
    if error := st.session_state.pop("watchlist-share-error", None):
        st.warning(error)
    st.markdown(f"<div class='watchlist-status'><span class='watchlist-status-dot'></span><b>{state['active']}</b><span>{len(symbols)} of 20 stocks</span><span class='watchlist-status-badge'>portable JSON</span><span>Saved in this browser session</span></div>", unsafe_allow_html=True)
    if not symbols:
        st.markdown("<div class='watchlist-empty'><b>This list is ready when you are.</b><span class='small-note'>Use the add-to-watchlist control on Dashboard or Screener to start collecting research candidates.</span></div>", unsafe_allow_html=True)
        return
    st.markdown("<div class='watchlist-section-head'><div><h2>Watchlist snapshot</h2><p>One-year price context and available Yahoo Finance fundamentals.</p></div><span class='small-note'>End-of-day data</span></div>", unsafe_allow_html=True)
    remove_col, remove_action_col, _ = st.columns([2.7, 1, 1.3], vertical_alignment="bottom")
    remove_symbols = remove_col.multiselect("Tidy this list", symbols, placeholder="Choose stocks to remove", key="remove-watchlist-symbols")
    if remove_action_col.button("Remove selected", key="remove-watchlist-button", use_container_width=True, disabled=not remove_symbols):
        st.session_state["watchlists"] = remove_from_watchlist(state, state["active"], remove_symbols)
        st.rerun()
    try:
        overview = yahoo_watchlist_overview(tuple(symbols))
    except (YahooChartError, ValueError):
        st.warning("Yahoo Finance watchlist data is temporarily unavailable. Try again shortly.")
        return
    positive_1m = int((overview["1M %"] > 0).sum())
    a, b, c, d = st.columns(4)
    a.metric("Constituents", len(overview), "Yahoo Finance snapshot")
    b.metric("Positive over 1M", positive_1m, f"{positive_1m / len(overview):.0%} of list")
    c.metric("Average 3M return", f"{overview['3M %'].mean():+.2f}%")
    d.metric("Fundamental coverage", f"{overview['pe'].notna().sum()}/{len(overview)}", "P/E available")
    st.dataframe(overview, use_container_width=True, hide_index=True, column_config={
        "Close": st.column_config.NumberColumn(format="Rs %.2f"), "1D %": st.column_config.NumberColumn(format="%+.2f%%"), "1M %": st.column_config.NumberColumn(format="%+.2f%%"), "3M %": st.column_config.NumberColumn(format="%+.2f%%"), "1Y %": st.column_config.NumberColumn(format="%+.2f%%"),
        "RSI-14": st.column_config.NumberColumn(format="%.1f"), "pe": st.column_config.NumberColumn("P/E", format="%.1f"), "pb": st.column_config.NumberColumn("P/B", format="%.1f"), "roe": st.column_config.NumberColumn("ROE", format="%.1f%%"), "dividend_yield": st.column_config.NumberColumn("Yield", format="%.1f%%"), "market_cap_cr": st.column_config.NumberColumn("Mkt cap", format="Rs %.0f Cr"),
    })
    with st.expander("AI watchlist overview", expanded=False):
        api_key, gemini_model = gemini_settings()
        if not api_key:
            st.info("Add GEMINI_API_KEY in Streamlit secrets to enable the AI overview.")
        elif st.button("Generate overview", key=f"watchlist-overview:{state['active']}"):
            facts = {"source": "Yahoo Finance daily EOD and fundamentals", "watchlist": state["active"], "stocks": json_records(overview, list(overview.columns), limit=20)}
            try:
                st.session_state[f"watchlist-ai:{state['active']}"] = ask_stock_comparison("Give a concise overview of this watchlist's 1M, 3M and 1Y performance, available fundamentals, and the most useful comparison to make next.", facts, [], api_key, gemini_model)
            except GeminiScreenerError as error:
                st.warning(str(error))
        answer = st.session_state.get(f"watchlist-ai:{state['active']}")
        if answer:
            st.markdown(answer)
    st.caption("Yahoo Finance fields are end-of-day and may be delayed. Watchlists are research aids, not investment advice.")


def dashboard(data: pd.DataFrame, updated: str):
    sectors, sectors_as_of = sector_snapshot(data)
    if sectors.empty:
        sentiment = "Sector analytics will appear after the initial market-close ingestion completes."
    else:
        leader, laggard = sectors.iloc[0], sectors.iloc[-1]
        sentiment = f"{safe_text(leader.industry)} leads the Nifty 200 universe ({leader.average_change_pct:+.2f}% equal-weight); {safe_text(laggard.industry)} trails ({laggard.average_change_pct:+.2f}%)."
    st.markdown(f"""<div class='topbar'>
      <div><span class='brand'>pai<b>saan</b></span><span class='small-note' style='margin-left:.7rem'>CapitalSense Advisors · pehchaan-first market desk</span></div>
      <div class='market-pill'><span class='live-dot'></span>Nifty 200 constituents · NSE Bhavcopy · {updated} · no FOMO</div>
    </div>""", unsafe_allow_html=True)
    market_tape(data)
    st.markdown(f"<section class='hero'><div class='eyebrow'>CapitalSense Advisors · equity desk</div><h1>more sense.<br><span class='glow'>less paisaan.</span></h1><p class='small-note' style='font-size:.98rem;max-width:42rem'>A focused read on the official Nifty 200 constituent universe—built for clearer market decisions.</p><div class='sentiment'>{sentiment}</div><div class='meme-note'>paisa + pehchaan = <b>paisaan</b> <span>· facts follow.</span></div></section>", unsafe_allow_html=True)
    st.markdown("<div class='source-note'>Universe: official Nifty 200 constituents · Prices: NSE Bhavcopy · Sector movement shown as equal-weighted constituent return.</div>", unsafe_allow_html=True)
    advances = int((data["Change %"] > 0).sum())
    declines = int((data["Change %"] < 0).sum())
    a, b, c, d = st.columns(4)
    a.metric("Nifty 200 universe", f"{len(data)} stocks", "official constituents")
    b.metric("Advance / decline", f"{advances} / {declines}", f"{advances / len(data):.0%} advancing")
    c.metric("Average daily move", f"{data['Change %'].mean():+.2f}%", "across universe")
    d.metric("Above previous close", f"{advances}", "live snapshot")
    left, right = st.columns([1.5, 1])
    with left:
        chart_select_col, watch_add_col = st.columns([5, 1], vertical_alignment="bottom")
        symbol = chart_select_col.selectbox("Chart symbol", data.Symbol.tolist(), index=0, label_visibility="collapsed")
        watch_add_col.markdown("<div class='small-note'>Watchlist</div>", unsafe_allow_html=True)
        watchlist_add_control([symbol], set(data["Symbol"]), f"dashboard:{symbol}")
        dashboard_range_col, dashboard_overlay_col = st.columns([1.4, 3.6], vertical_alignment="bottom")
        dashboard_range = dashboard_range_col.radio("Chart range", ["3M", "6M", "1Y", "3Y"], index=2, horizontal=True, key="dashboard-chart-range")
        dashboard_overlays = dashboard_overlay_col.multiselect("Add moving averages", OVERLAYS, default=[], key="dashboard-chart-overlays", help="Start with price only; add an overlay only when it helps answer a specific question.")
        resolved_symbol = yahoo_symbol(symbol)
        cache_key = f"dashboard_yahoo_chart:{resolved_symbol}:3y:1d:{ADJUSTMENT_CONTRACT}"
        try:
            history, stale = load_with_last_valid(lambda: yahoo_chart_history(resolved_symbol, "3y", "1d", ADJUSTMENT_CONTRACT), st.session_state.get(cache_key))
            st.session_state[cache_key] = history
            st.markdown(f"<div class='panel-title'>{safe_text(symbol)}</div><div class='panel-subtitle'>{dashboard_range} Yahoo Finance daily price view</div>", unsafe_allow_html=True)
            st.plotly_chart(market_chart(history, resolved_symbol, dashboard_overlays, days=YAHOO_WINDOWS[dashboard_range], rsi_lines=[(30, "RSI 30"), (70, "RSI 70")], height=460, show_volume_sma=bool(dashboard_overlays)), use_container_width=True, config={"displaylogo": False, "scrollZoom": True})
            if stale:
                st.caption("Showing the last valid Yahoo Finance chart from this session.")
        except (YahooChartError, ValueError):
            st.warning("This Yahoo Finance chart is temporarily unavailable. The rest of the market snapshot is still current.")
    with right:
        st.markdown("<div class='panel-title'>Today’s moves</div><div class='panel-subtitle'>Nifty 200 leaders & laggards</div>", unsafe_allow_html=True)
        gainers, losers = st.tabs(["Top gainers", "Top losers"])
        with gainers:
            for _, row in data.nlargest(4, "Change %").iterrows():
                mover_row(row)
        with losers:
            for _, row in data.nsmallest(4, "Change %").iterrows():
                mover_row(row)

    st.markdown(f"<div class='section-title'>Sector pulse <span class='small-note'>/ vibe check</span></div><p class='section-copy'>Equal-weighted movement across the cached Nifty 200 quote snapshot{f' · as of {sectors_as_of}' if sectors_as_of else ''}.</p>", unsafe_allow_html=True)
    sector_cols = st.columns(4)
    if sectors.empty:
        st.info("Sector aggregates are not available yet. Run the market-close ingestion task to populate them.")
    else:
        for column, (_, sector) in zip(sector_cols, sectors.head(4).iterrows()):
            dot = GREEN if sector.average_change_pct >= 0 else RED
            column.markdown(f"<div class='sector-chip'><i class='sector-dot' style='background:{dot}'></i><b>{safe_text(sector.industry)}</b><span style='margin-left:auto'>{gain(sector.average_change_pct)}</span></div><div class='small-note'>{int(sector.advancers)} up · {int(sector.decliners)} down · {int(sector.members)} stocks</div>", unsafe_allow_html=True)
        shown_sectors = sectors[["industry", "members", "average_change_pct", "advancers", "decliners", "turnover"]].copy()
        shown_sectors["average_change_pct"] = shown_sectors["average_change_pct"].map(lambda value: f"{value:+.2f}%")
        shown_sectors["turnover"] = shown_sectors["turnover"].map(lambda value: f"₹{value / 10_000_000:,.1f} Cr")
        st.dataframe(shown_sectors, use_container_width=True, hide_index=True, column_config={"average_change_pct": "Average move"})


def legacy_screener(data: pd.DataFrame):
    st.caption("No FOMO filters—just a fast, full-universe EOD screen. Historical technical filters need persistent infrastructure, so they are intentionally not represented as current data here.")
    st.caption(f"Coverage: {len(data)} / 200 verified constituents · EOD snapshot date: {data['date'].iloc[0]}")


def screener(data: pd.DataFrame):
    """An EOD scanner with opt-in Yahoo fundamental enrichment."""
    st.markdown("""
    <section class='screener-hero'>
      <div class='screener-hero-top'>
        <div class='screener-hero-copy'>
          <div class='screener-kicker'>Nifty 200 EOD market scanner</div>
          <h1>Find the move. Keep the context.</h1>
          <div class='small-note'>Move from a 200-stock view to a focused research set—without treating one-day data as a decision.</div>
        </div>
        <div class='screener-hero-note'><b style='color:#e9eef3'>How to read this page</b><br>Start broad, add precision only when it earns its place, then compare a short list on the same 1-year lens.</div>
      </div>
      <div class='guide-steps'>
        <div class='guide-step'><span class='guide-number'>1</span><b>Scan</b><p>Use a quick scan, search, industry and ranking to find the current setup.</p></div>
        <div class='guide-step'><span class='guide-number'>2</span><b>Refine</b><p>Open Refine scan for price or range filters; use Yahoo fundamentals only for a deeper screen.</p></div>
        <div class='guide-step'><span class='guide-number'>3</span><b>Compare</b><p>Select 2–5 names for Yahoo snapshots, 1-year charts, Nifty 50 relative returns and follow-up questions.</p></div>
      </div>
    </section>
    """, unsafe_allow_html=True)
    preset = st.radio("Quick scan", ["All stocks", "Top gainers", "Near day high", "Pullbacks"], horizontal=True)
    search_col, industry_col, sort_col = st.columns([1.35, 1.15, 1])
    query = search_col.text_input("Search company or symbol", placeholder="e.g. Reliance, TCS, BANK")
    industry = industry_col.selectbox("Industry", ["All"] + sorted(data.Industry.dropna().unique().tolist()))
    sort_label = sort_col.selectbox("Rank results by", ["Daily move", "Near day high", "Price"])
    with st.expander("Refine scan", expanded=False):
        change_min_col, change_max_col = st.columns(2)
        min_change = change_min_col.number_input("Minimum daily move (%)", value=0.0, step=0.25)
        max_change = change_max_col.number_input("Maximum daily move (%)", value=0.0, step=0.25, help="Set a value only when you want to cap the move.")
        price_min_col, price_max_col, range_col = st.columns(3)
        min_price = price_min_col.number_input("Minimum price (Rs)", min_value=0.0, value=0.0, step=50.0)
        max_price = price_max_col.number_input("Maximum price (Rs)", min_value=0.0, value=0.0, step=50.0)
        min_day_range_position = range_col.slider("Close in top of day range (%)", 0, 100, 0, help="100 means the close was at the day's high; 50 means mid-range.")

    result = screened_stocks(
        data,
        industry if industry != "All" else None,
        query,
        min_change if min_change != 0 else None,
        max_change if max_change != 0 else None,
        min_price if min_price > 0 else None,
        max_price if max_price > 0 else None,
        float(min_day_range_position) if min_day_range_position > 0 else None,
    )
    preset_copy = "Full verified universe"
    if preset == "Top gainers":
        result = result[result["Change %"] > 0]
        preset_copy = "Positive daily movers"
    elif preset == "Near day high":
        result = result[result["Day range %"] >= 85]
        preset_copy = "Closing in the top 15 percent of today’s range"
    elif preset == "Pullbacks":
        result = result[result["Change %"] < 0]
        preset_copy = "Negative daily movers"

    fundamental_query = st.text_input(
        "Describe your fundamental screen",
        placeholder="Find reasonably valued companies with strong returns on equity and a dividend",
        help="AI can translate normal language into the available Yahoo Finance filters: P/E, P/B, ROE, dividend yield and market cap.",
    )
    if fundamental_query.strip():
        api_key, gemini_model = gemini_settings()
        ai_enabled = st.toggle("Use Gemini to interpret my request", value=bool(api_key), disabled=not bool(api_key))
        if not api_key:
            st.caption("Add GEMINI_API_KEY in Streamlit secrets to enable AI interpretation. Manual rules such as 'PE under 25 and ROE above 15%' still work.")
        rules = None
        try:
            if ai_enabled:
                interpretation_key = f"gemini-rules:{fundamental_query.strip()}"
                if st.button("Interpret with Gemini", type="primary"):
                    st.session_state[interpretation_key] = translate_screener_request(fundamental_query, api_key, gemini_model)
                interpretation = st.session_state.get(interpretation_key)
                if interpretation is None:
                    st.info("Gemini will translate your sentence into supported, reviewable filters before Yahoo Finance data is requested.")
                    return
                rules, summary = interpretation
                st.caption(f"Gemini interpretation: {safe_text(summary)}")
            else:
                rules = parse_fundamental_query(fundamental_query)
            rule_summary = " and ".join(f"{FIELD_LABELS[rule.field]} {rule.operator} {rule.value:g}" for rule in rules)
            st.caption(f"Applied rules: {rule_summary}")
            fundamental_key = f"fundamentals:{tuple(result['Symbol'].tolist())}"
            if st.button(f"Run fundamental screen across {len(result)} stocks"):
                st.session_state[fundamental_key] = yahoo_fundamentals(tuple(result["Symbol"].tolist()))
            fundamentals = st.session_state.get(fundamental_key)
            if fundamentals is None:
                st.info("Rules are ready. Run the screen when you want to enrich this EOD shortlist; results are cached for six hours.")
                return
            result = filter_fundamentals(result.merge(fundamentals, on="Symbol", how="left"), rules)
            preset_copy = f"{preset_copy} plus Yahoo fundamentals"
        except (ValueError, GeminiScreenerError, YahooChartError) as error:
            st.warning(str(error))
            return

    sort_columns = {"Daily move": "Change %", "Near day high": "Day range %", "Price": "Price"}
    result = result.sort_values(sort_columns[sort_label], ascending=False).reset_index(drop=True)
    st.markdown(f"<div class='scan-summary'><b>{len(result)} matches</b> · {safe_text(preset_copy)} · {len(data)} / 200 verified constituents · EOD snapshot: {safe_text(data['date'].iloc[0])}</div>", unsafe_allow_html=True)
    if result.empty:
        st.info("No stocks match this scan. Loosen a filter or choose All stocks.")
        return
    matched_advancers = int((result["Change %"] > 0).sum())
    metric_a, metric_b, metric_c, metric_d = st.columns(4)
    metric_a.metric("Matches", len(result), f"of {len(data)} constituents")
    metric_b.metric("Advancing", matched_advancers, f"{matched_advancers / len(result):.0%} of scan")
    metric_c.metric("Average move", f"{result['Change %'].mean():+.2f}%")
    metric_d.metric("Industries", result["Industry"].nunique(), "represented in scan")
    shown_columns = ["Symbol", "Company", "Industry", "Price", "Change %", "Day range %"]
    if fundamental_query.strip():
        shown_columns += [column for column in ("pe", "pb", "roe", "dividend_yield", "market_cap_cr") if column in result]
    shown = result[shown_columns].copy()
    shown.insert(0, "Rank", range(1, len(shown) + 1))
    column_config = {
        "Rank": st.column_config.NumberColumn(width="small"),
        "Price": st.column_config.NumberColumn("Last price", format="Rs %.2f"),
        "Change %": st.column_config.NumberColumn("Day move", format="%+.2f%%"),
        "Day range %": st.column_config.ProgressColumn("Close in day range", format="%.0f%%", min_value=0, max_value=100),
        "pe": st.column_config.NumberColumn("P/E", format="%.1f"),
        "pb": st.column_config.NumberColumn("P/B", format="%.1f"),
        "roe": st.column_config.NumberColumn("ROE", format="%.1f%%"),
        "dividend_yield": st.column_config.NumberColumn("Yield", format="%.1f%%"),
        "market_cap_cr": st.column_config.NumberColumn("Mkt cap", format="Rs %.0f Cr"),
    }
    st.dataframe(shown, use_container_width=True, hide_index=True, height=min(560, 70 + len(shown) * 35), column_config=column_config)
    st.divider()
    show_trendlyne_compare = st.toggle("Compare QVT and SWOT scores with Trendlyne", key="trendlyne-screener-toggle", help="Uses Trendlyne's public widgets for an additional quality, valuation, technical and SWOT view. Open only when you want this third-party data.")
    if show_trendlyne_compare:
        comparison_symbols = st.multiselect(
            "Choose up to 5 screened stocks",
            result["Symbol"].tolist(),
            default=result["Symbol"].head(min(2, len(result))).tolist(),
            max_selections=5,
            key="trendlyne-screener-symbols",
        )
        if comparison_symbols:
            st.caption("Trendlyne widgets are provider-supplied and may use a different update schedule than the NSE and Yahoo Finance panels above.")
            score_tabs = st.tabs(comparison_symbols)
            for tab, comparison_symbol in zip(score_tabs, comparison_symbols):
                with tab:
                    qvt_col, swot_col = st.columns(2)
                    with qvt_col:
                        st.markdown("<div class='panel-title'>QVT score</div><div class='panel-subtitle'>Quality · valuation · technicals</div>", unsafe_allow_html=True)
                        trendlyne_widget("qvt-widget", comparison_symbol, 365)
                    with swot_col:
                        st.markdown("<div class='panel-title'>SWOT view</div><div class='panel-subtitle'>Strengths · weaknesses · opportunities · threats</div>", unsafe_allow_html=True)
                        trendlyne_widget("swot-widget", comparison_symbol, 365)
        else:
            st.info("Choose one to five stocks from this screen to open their Trendlyne scorecards.")
    research_workbench(result, str(data["date"].iloc[0]), preset_copy, sort_label)
    inspect_col, action_col, watch_add_col = st.columns([3, 1, 1], vertical_alignment="bottom")
    inspect_symbol = inspect_col.selectbox("Inspect a result in Charts", result["Symbol"].tolist(), key="screener_inspect_symbol")

    action_col.button("Open chart", use_container_width=True, on_click=open_chart_for, args=(inspect_symbol,))
    watch_add_col.markdown("<div class='small-note'>Watchlist</div>", unsafe_allow_html=True)
    watchlist_add_control([inspect_symbol], set(data["Symbol"]), f"screener:{inspect_symbol}")
    st.caption("NSE fields use the latest cached Bhavcopy. Yahoo fundamentals are provider-reported and may be missing or delayed. This is a descriptive screen, not investment advice.")


def charts(data: pd.DataFrame):
    st.markdown("""
    <section class='chart-hero'>
      <div class='screener-kicker'>Yahoo Finance · daily EOD technical view</div>
      <h1>Read the setup. Then ask the chart.</h1>
      <div class='small-note'>Use one symbol at a time; the controls change the evidence on screen, not a recommendation.</div>
      <div class='chart-guide'>
        <div class='chart-guide-item'><b>1. Set the window</b>Use the range to judge whether a move is short-term noise or part of a larger structure.</div>
        <div class='chart-guide-item'><b>2. Keep overlays intentional</b>EMA/SMA show trend context; RSI and volume help test momentum and participation.</div>
        <div class='chart-guide-item'><b>3. Ask one decision question</b>Open Ask this chart for a focused follow-up, then verify it against the visible chart.</div>
      </div>
    </section>
    """, unsafe_allow_html=True)
    symbol_col, range_col = st.columns([1.25, 3.75], vertical_alignment="bottom")
    symbol = symbol_col.selectbox("Symbol", data.Symbol.tolist(), key="chart_symbol")
    range_label = range_col.radio("Range", list(YAHOO_WINDOWS), horizontal=True, index=2)
    row = data.set_index("Symbol").loc[symbol]
    resolved_symbol = yahoo_symbol(symbol)
    st.markdown(f"<div class='chart-heading' style='font-size:1.42rem;margin-top:.25rem'>{safe_text(symbol)} &nbsp; ₹{row.Price:,.2f} &nbsp; {gain(row['Change %'])}</div>", unsafe_allow_html=True)
    overlays, levels = st.columns([2, 1])
    selected_overlays = overlays.multiselect("Price overlays", OVERLAYS, default=["EMA9", "EMA21", "SMA50", "SMA200"])
    selected_levels = levels.multiselect("RSI levels", [30, 35, 50, 70], default=[30, 70])
    cache_key = f"last_yahoo_chart:{resolved_symbol}:3y:1d:{ADJUSTMENT_CONTRACT}"
    try:
        history, stale = load_with_last_valid(lambda: yahoo_chart_history(resolved_symbol, "3y", "1d", ADJUSTMENT_CONTRACT), st.session_state.get(cache_key))
        st.session_state[cache_key] = history
    except (YahooChartError, ValueError):
        st.error("Daily chart data is temporarily unavailable. Try again shortly.")
        return
    if stale:
        st.warning("Yahoo Finance could not refresh this chart. Showing the last valid chart from this session.")
    latest = history.iloc[-1]
    metric_columns = st.columns(5)
    metric_columns[0].metric("RSI-14", f"{latest['RSI14']:.1f}" if pd.notna(latest["RSI14"]) else "—")
    metric_columns[1].metric("EMA-9", f"₹{latest['EMA9']:,.2f}" if pd.notna(latest["EMA9"]) else "—")
    metric_columns[2].metric("SMA-50", f"₹{latest['SMA50']:,.2f}" if pd.notna(latest["SMA50"]) else "—")
    metric_columns[3].metric("SMA-200", f"₹{latest['SMA200']:,.2f}" if pd.notna(latest["SMA200"]) else "—")
    metric_columns[4].metric("Latest close", f"₹{latest['Close']:,.2f}")
    rsi_lines = [(level, f"RSI {level}") for level in selected_levels]
    figure = market_chart(history, resolved_symbol, selected_overlays, days=YAHOO_WINDOWS[range_label], rsi_lines=rsi_lines)
    st.plotly_chart(figure, use_container_width=True, config={"displaylogo": False, "scrollZoom": True})
    show_trendlyne_technicals = st.toggle("Show Trendlyne technical panel", key="trendlyne-chart-toggle", help="Opens Trendlyne's third-party technical widget for the chart symbol.")
    if show_trendlyne_technicals:
        st.markdown(f"<div class='section-title'>Trendlyne technicals <span class='small-note'>/ {safe_text(symbol)}</span></div><p class='section-copy'>A provider-supplied technical snapshot alongside the Yahoo Finance chart above.</p>", unsafe_allow_html=True)
        trendlyne_widget("technical-widget", symbol, 550)
    chart_question_chat(history, symbol, range_label)
    st.caption(f"Provider: Yahoo Finance · {resolved_symbol} · daily EOD data · latest market date: {latest['Date']:%d %b %Y} · adjusted OHLC contract: {ADJUSTMENT_CONTRACT}")


inject_css()
try:
    data, updated = live_universe()
except Exception as error:
    st.error(f"NSE data could not be loaded: {error}")
    if st.button("Try NSE data again"):
        live_universe.clear()
        st.rerun()
    st.stop()
import_shared_watchlist_from_url(set(data["Symbol"]))
with st.sidebar:
    st.markdown("<div class='brand'>pai<b>saan</b></div><p class='small-note'>CapitalSense Advisors</p>", unsafe_allow_html=True)
    page = st.radio("Navigate", ["Dashboard", "Screener", "Charts", "Watchlists"], label_visibility="collapsed", key="page")
    st.divider()
    st.markdown("<div class='eyebrow'>Data mode</div>", unsafe_allow_html=True)
    if st.button("Refresh NSE data", use_container_width=True):
        allowed, remaining = refresh_gate().request()
        if allowed:
            live_universe.clear()
            yahoo_chart_history.clear()
            yahoo_fundamentals.clear()
            st.rerun()
        st.caption(f"Refresh available in {remaining}s.")
    st.success("Direct NSE data")
    st.caption("Official Nifty 200 constituents · cached in Streamlit · no jaldibaazi")
    st.caption("Market data is informational only; it is not investment advice.")

if page == "Dashboard":
    dashboard(data, updated)
elif page == "Screener":
    screener(data)
elif page == "Charts":
    charts(data)
elif page == "Watchlists":
    watchlist_page(data)
