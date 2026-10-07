from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st
import altair as alt

st.set_page_config(page_title="paisaan · CapitalSense Advisors", page_icon="₹", layout="wide")

ACCENT, GREEN, RED, MUTED = "#2bd4a4", "#2bd4a4", "#ff6b6b", "#8d98a7"


def inject_css():
    st.markdown("""
    <style>
      .stApp { background: radial-gradient(54% 35% at 86% -5%, #174c3a 0%, transparent 55%), radial-gradient(36% 25% at 45% 0%, #20244d 0%, transparent 68%), #070a0e; }
      .block-container { max-width: 1440px; padding-top: .9rem; padding-bottom: 2.5rem; }
      [data-testid="stSidebar"] { background: linear-gradient(180deg, #0c1117, #080b10); border-right: 1px solid #222a33; }
      [data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }
      .brand { font-size: 1.4rem; font-weight: 750; letter-spacing: -0.06em; }
      .brand b { color: #2bd4a4; }
      .eyebrow { color: #8d98a7; text-transform: uppercase; font-size: .72rem; letter-spacing: .14em; }
      .topbar { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding: .35rem 0 1.2rem; }
      .live-dot { display:inline-block; width:7px; height:7px; border-radius:999px; background:#2bd4a4; box-shadow: 0 0 0 5px rgba(43,212,164,.12); margin-right:.5rem; }
      .market-pill { border:1px solid #23323a; background:rgba(13,23,27,.76); padding:.45rem .75rem; border-radius:999px; color:#b9c3ce; font-size:.78rem; }
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
      .small-note { color: #8d98a7; font-size: .78rem; }
      .stButton button { border-radius: 999px; border-color: #315448; font-weight:600; }
      .stDataFrame { border:1px solid #242d37; border-radius:14px; overflow:hidden; }
      [data-testid="stRadio"] label { border-radius:9px; }
      [data-testid="stRadio"] { gap: .45rem; }
      [data-testid="stRadio"] label { padding: .15rem .25rem; }
      .chart-heading { font-size:1.55rem; font-weight:700; letter-spacing:-.045em; margin:0 0 .6rem; }
      .chart-meta { color:#8d98a7; font-size:.82rem; margin-top:-.35rem; margin-bottom:.65rem; }
      </style>
    """, unsafe_allow_html=True)


API_BASE_URL = os.getenv("STREAMLIT_API_BASE_URL", "http://localhost:8000")


@st.cache_data(ttl=600, show_spinner="Loading official Nifty 200 data from NSE MCP…")
def live_universe() -> tuple[pd.DataFrame, str]:
    """Read market data from the API; the UI never calls NSE MCP directly."""
    response = httpx.get(f"{API_BASE_URL}/v1/market/overview", params={"index": "NIFTY200"}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    frame = pd.DataFrame(payload["constituents"]).rename(columns={"symbol": "Symbol", "company": "Company", "industry": "Industry", "close": "Price", "pct_change": "Change %", "volume": "Volume", "high": "Day High", "low": "Day Low", "prev_close": "Previous Close"})
    if frame.empty:
        raise RuntimeError("The API returned no Nifty 200 rows.")
    return frame, payload.get("as_of", "unknown")


RANGES = {"1D": 1, "1W": 1, "1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36}


@st.cache_data(ttl=3600, show_spinner="Loading historical NSE bhavcopy data…")
def stock_history(symbol: str, months_needed: int) -> pd.DataFrame:
    """Read chart bars from the API; backend handles source access and caching."""
    range_for_months = {1: "1M", 3: "3M", 6: "6M", 12: "1Y", 36: "3Y"}
    response = httpx.get(f"{API_BASE_URL}/v1/stocks/{symbol}/bars", params={"range": range_for_months[months_needed]}, timeout=45)
    response.raise_for_status()
    history = pd.DataFrame(response.json()["bars"]).drop_duplicates(subset="date").sort_values("date")
    if history.empty:
        raise RuntimeError(f"No Bhavcopy history is available for {symbol}.")
    history["date"] = pd.to_datetime(history["date"])
    return history


def display_chart(history: pd.DataFrame, candle: bool, long_range: bool = False):
    """Fast Vega-Lite market chart; older history is downsampled before render."""
    view = history.copy()
    if long_range and len(view) > 260:
        view = view.set_index("date").resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna().reset_index()
    base = alt.Chart(view).encode(x=alt.X("date:T", title=None, axis=alt.Axis(grid=False, labelColor=MUTED)), tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip("open:Q", title="Open", format=".2f"), alt.Tooltip("high:Q", title="High", format=".2f"), alt.Tooltip("low:Q", title="Low", format=".2f"), alt.Tooltip("close:Q", title="Close", format=".2f")])
    if candle:
        color = alt.condition("datum.open <= datum.close", alt.value(GREEN), alt.value(RED))
        chart = base.mark_rule().encode(y=alt.Y("low:Q", title=None, scale=alt.Scale(zero=False), axis=alt.Axis(gridColor="#202932", labelColor=MUTED)), y2="high:Q", color=color) + base.mark_bar(size=7).encode(y=alt.Y("open:Q", scale=alt.Scale(zero=False)), y2="close:Q", color=color)
    else:
        chart = base.mark_area(line={"color": ACCENT, "strokeWidth": 2.5}, color=alt.Gradient(gradient="linear", stops=[alt.GradientStop(color="rgba(43,212,164,.22)", offset=0), alt.GradientStop(color="rgba(43,212,164,0)", offset=1)], x1=1, x2=1, y1=1, y2=0)).encode(y=alt.Y("close:Q", title=None, axis=alt.Axis(gridColor="#202932", labelColor=MUTED)))
    return chart.properties(height=315).resolve_scale(y="shared").configure_view(strokeOpacity=0).configure_axis(domain=False, tickColor="#202932")


def gain(value: float) -> str:
    return f"<span class='{ 'gain' if value >= 0 else 'loss' }'>{value:+.2f}%</span>"


def dashboard(data: pd.DataFrame, updated: str):
    st.markdown("""<div class='topbar'>
      <div><span class='brand'>pai<b>saan</b></span><span class='small-note' style='margin-left:.7rem'>CapitalSense Advisors · market desk</span></div>
      <div class='market-pill'><span class='live-dot'></span>Nifty 200 constituents · NSE Bhavcopy · {updated}</div>
    </div>""", unsafe_allow_html=True)
    st.markdown("<section class='hero'><div class='eyebrow'>CapitalSense Advisors · equity desk</div><h1>more sense.<br><span class='glow'>less paisaan.</span></h1><p class='small-note' style='font-size:.98rem;max-width:42rem'>A focused read on the official Nifty 200 constituent universe—built for clearer market decisions.</p></section>", unsafe_allow_html=True)
    st.write("")
    advances = int((data["Change %"] > 0).sum())
    declines = int((data["Change %"] < 0).sum())
    a, b, c, d = st.columns(4)
    a.metric("Nifty 200 universe", f"{len(data)} stocks", "official constituents")
    b.metric("Advance / decline", f"{advances} / {declines}", f"{advances / len(data):.0%} advancing")
    c.metric("Average daily move", f"{data['Change %'].mean():+.2f}%", "across universe")
    d.metric("Above previous close", f"{advances}", "live snapshot")
    left, right = st.columns([1.55, 1])
    with left:
        symbol = st.selectbox("Chart symbol", data.Symbol.tolist(), index=0, label_visibility="collapsed")
        history = stock_history(symbol, 3)
        st.markdown(f"<div class='panel-title'>{symbol}</div><div class='panel-subtitle'>3-month Bhavcopy close</div>", unsafe_allow_html=True)
        st.altair_chart(display_chart(history, candle=False), use_container_width=True)
    with right:
        st.markdown("<div class='panel-title'>Today’s moves</div><div class='panel-subtitle'>Nifty 200 leaders & laggards</div><br>", unsafe_allow_html=True)
        for _, row in data.sort_values("Change %", ascending=False).head(5).iterrows():
            strength = min(abs(row['Change %']) / 13 * 100, 100)
            color = "#2bd4a4" if row['Change %'] >= 0 else "#ff6b6b"
            st.markdown(f"<div class='feed'><b>{row['Symbol']}</b><span style='float:right'>{gain(row['Change %'])}</span><br><span class='small-note'>{row['Industry']} · ₹{row['Price']:,.2f} · {row['Volume']:,.0f} shares</span><div class='move-bar'><div class='move-fill' style='width:{strength:.0f}%;background:{color}'></div></div></div>", unsafe_allow_html=True)
        st.caption("Illustrative market snapshot. Not investment advice.")


def screener(data: pd.DataFrame):
    st.header("Screener")
    x, y, z = st.columns(3)
    industry = x.selectbox("Industry", ["All"] + sorted(data.Industry.dropna().unique().tolist()))
    move = y.selectbox("Daily move", ["Any", "Gainers", "Losers"])
    query = z.text_input("Search symbol")
    result = data.copy()
    if industry != "All": result = result[result.Industry == industry]
    if move == "Gainers": result = result[result["Change %"] > 0]
    if move == "Losers": result = result[result["Change %"] < 0]
    if query: result = result[result.Symbol.str.contains(query.upper())]
    shown = result[["Symbol", "Company", "Industry", "Price", "Change %", "Volume", "Day High", "Day Low"]].copy()
    shown["Price"] = shown.Price.map(lambda n: f"₹{n:,.2f}")
    shown["Change %"] = shown["Change %"].map(lambda n: f"{n:+.2f}%")
    st.dataframe(shown, use_container_width=True, hide_index=True)
    st.caption("Filters are local to this learning build. Feed live data through the NSE MCP panel in the sidebar.")


def charts(data: pd.DataFrame):
    st.markdown("<div class='chart-heading'>Charts</div><div class='chart-meta'>Live NSE price snapshot with historical Bhavcopy data</div>", unsafe_allow_html=True)
    symbol_col, range_col = st.columns([1.25, 3.75], vertical_alignment="bottom")
    symbol = symbol_col.selectbox("Symbol", data.Symbol.tolist())
    range_label = range_col.radio("Range", list(RANGES), horizontal=True, index=2)
    row = data.set_index("Symbol").loc[symbol]
    st.markdown(f"<div class='chart-heading' style='font-size:1.42rem;margin-top:.25rem'>{symbol} &nbsp; ₹{row.Price:,.2f} &nbsp; {gain(row['Change %'])}</div>", unsafe_allow_html=True)
    history = stock_history(symbol, RANGES[range_label])
    if range_label == "1D":
        history = history.tail(1)
    elif range_label == "1W":
        history = history.tail(5)
    st.altair_chart(display_chart(history, candle=range_label in {"1D", "1W", "1M"}, long_range=range_label in {"1Y", "3Y"}), use_container_width=True)
    st.caption(f"{len(history)} NSE Bhavcopy observations · {history.date.min():%d %b %Y} to {history.date.max():%d %b %Y}")


def watchlist(data: pd.DataFrame):
    st.header("Watchlist")
    st.write("A quiet place for the names you want to follow.")
    selected = st.multiselect("Your list", data.Symbol.tolist(), default=data.Symbol.head(3).tolist())
    st.dataframe(data[data.Symbol.isin(selected)], use_container_width=True, hide_index=True)


def news():
    st.header("News")
    for title, source, time in [
        ("Market breadth improves as large caps lead the session", "Market desk", "Today"),
        ("Earnings calendar: what to watch this week", "Company filings", "Today"),
        ("Sector snapshot: financials and energy", "Market desk", "Yesterday"),
    ]:
        st.markdown(f"<div class='feed'><b>{title}</b><br><span class='small-note'>{source} · {time}</span></div>", unsafe_allow_html=True)


inject_css()
try:
    data, updated = live_universe()
except Exception as error:
    st.error(f"NSE data could not be loaded: {error}")
    st.stop()
with st.sidebar:
    st.markdown("<div class='brand'>pai<b>saan</b></div><p class='small-note'>CapitalSense Advisors</p>", unsafe_allow_html=True)
    page = st.radio("Navigate", ["Dashboard", "Screener", "Charts", "Watchlist", "News"], label_visibility="collapsed")
    st.divider()
    st.markdown("<div class='eyebrow'>Data mode</div>", unsafe_allow_html=True)
    st.success("Live market API")
    st.caption("Official Nifty 200 constituents · cached server data")

{"Dashboard": dashboard, "Screener": screener, "Charts": charts, "Watchlist": watchlist, "News": news}[page](data, updated) if page == "Dashboard" else {"Screener": screener, "Charts": charts, "Watchlist": watchlist}[page](data) if page != "News" else news()
