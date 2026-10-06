from __future__ import annotations

from datetime import datetime
import random

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from nse_mcp import BHAVCOPY_URL, CM_MARKET_URL, call_nse_tool, list_tools

st.set_page_config(page_title="InvestorPaisa · Streamlit", page_icon="◒", layout="wide")

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
      </style>
    """, unsafe_allow_html=True)


@st.cache_data(ttl=60)
def demo_universe() -> pd.DataFrame:
    return pd.DataFrame([
        ("TRENT", "Consumer", 5577.20, 12.64, "Strong momentum"),
        ("MOTILALOFS", "Financials", 1096.30, 6.93, "Above 50D average"),
        ("TIINDIA", "Auto", 4297.10, 6.58, "Volume expansion"),
        ("COALINDIA", "Energy", 411.65, -3.16, "Below 20D average"),
        ("PHOENIXLTD", "Realty", 1567.50, -2.66, "RSI cooling"),
        ("RELIANCE", "Energy", 1432.50, 1.28, "Above 200D average"),
        ("HDFCBANK", "Financials", 972.40, .71, "Near breakout"),
        ("INFY", "IT", 1618.80, -0.45, "Range-bound"),
        ("TATAMOTORS", "Auto", 702.10, 2.36, "Volume expansion"),
        ("SUNPHARMA", "Healthcare", 1772.80, 1.07, "Strong momentum"),
    ], columns=["Symbol", "Sector", "Price", "Change %", "Signal"])


def price_chart(symbol: str):
    random.seed(symbol)
    dates = pd.date_range(end=datetime.now(), periods=90)
    base = demo_universe().set_index("Symbol").loc[symbol, "Price"]
    prices = []
    current = base * .91
    for _ in dates:
        current *= 1 + random.uniform(-.022, .026)
        prices.append(current)
    fig = go.Figure(go.Scatter(x=dates, y=prices, mode="lines", line=dict(color=ACCENT, width=2.5), fill="tozeroy", fillcolor="rgba(43,212,164,.13)"))
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(showgrid=False, color=MUTED), yaxis=dict(gridcolor="#202932", color=MUTED), showlegend=False)
    return fig


def gain(value: float) -> str:
    return f"<span class='{ 'gain' if value >= 0 else 'loss' }'>{value:+.2f}%</span>"


def dashboard(data: pd.DataFrame):
    st.markdown("""<div class='topbar'>
      <div><span class='brand'>Investor<b>Paisa</b></span><span class='small-note' style='margin-left:.7rem'>Your calm market desk</span></div>
      <div class='market-pill'><span class='live-dot'></span>Market closed · Last updated 16:10 IST</div>
    </div>""", unsafe_allow_html=True)
    st.markdown("<section class='hero'><div class='eyebrow'>Market desk · Nifty 200</div><h1>the market,<br><span class='glow'>minus the noise.</span></h1><p class='small-note' style='font-size:.98rem;max-width:42rem'>A focused read on breadth, leadership and momentum—without the clutter.</p></section>", unsafe_allow_html=True)
    st.write("")
    a, b, c, d = st.columns(4)
    a.metric("NIFTY 50", "22,776.10", "+0.98%")
    b.metric("Advance / decline", "141 / 57", "71% advancing")
    c.metric("Nifty 200 above 50D", "126", "+8 today")
    d.metric("Market status", "Closed", "6 Oct 2026")
    left, right = st.columns([1.55, 1])
    with left:
        st.markdown("<div class='panel-title'>NIFTY 50</div><div class='panel-subtitle'>90-day price action · illustrative data</div>", unsafe_allow_html=True)
        st.plotly_chart(price_chart("RELIANCE"), use_container_width=True, config={"displayModeBar": False})
    with right:
        st.markdown("<div class='panel-title'>Today’s moves</div><div class='panel-subtitle'>Nifty 200 leaders & laggards</div><br>", unsafe_allow_html=True)
        for _, row in data.sort_values("Change %", ascending=False).head(5).iterrows():
            strength = min(abs(row['Change %']) / 13 * 100, 100)
            color = "#2bd4a4" if row['Change %'] >= 0 else "#ff6b6b"
            st.markdown(f"<div class='feed'><b>{row['Symbol']}</b><span style='float:right'>{gain(row['Change %'])}</span><br><span class='small-note'>{row['Sector']} · ₹{row['Price']:,.2f}</span><div class='move-bar'><div class='move-fill' style='width:{strength:.0f}%;background:{color}'></div></div></div>", unsafe_allow_html=True)
        st.caption("Illustrative market snapshot. Not investment advice.")


def screener(data: pd.DataFrame):
    st.header("Screener")
    x, y, z = st.columns(3)
    sector = x.selectbox("Sector", ["All"] + sorted(data.Sector.unique().tolist()))
    move = y.selectbox("Daily move", ["Any", "Gainers", "Losers"])
    query = z.text_input("Search symbol")
    result = data.copy()
    if sector != "All": result = result[result.Sector == sector]
    if move == "Gainers": result = result[result["Change %"] > 0]
    if move == "Losers": result = result[result["Change %"] < 0]
    if query: result = result[result.Symbol.str.contains(query.upper())]
    shown = result.copy()
    shown["Price"] = shown.Price.map(lambda n: f"₹{n:,.2f}")
    shown["Change %"] = shown["Change %"].map(lambda n: f"{n:+.2f}%")
    st.dataframe(shown, use_container_width=True, hide_index=True)
    st.caption("Filters are local to this learning build. Feed live data through the NSE MCP panel in the sidebar.")


def charts(data: pd.DataFrame):
    st.header("Charts")
    symbol = st.selectbox("Symbol", data.Symbol.tolist(), index=5)
    row = data.set_index("Symbol").loc[symbol]
    st.markdown(f"### {symbol} &nbsp; ₹{row.Price:,.2f} &nbsp; {gain(row['Change %'])}", unsafe_allow_html=True)
    st.plotly_chart(price_chart(symbol), use_container_width=True, config={"displayModeBar": False})
    st.info("This screen is for exploring layout and MCP-powered data plumbing, not trading advice.")


def watchlist(data: pd.DataFrame):
    st.header("Watchlist")
    st.write("A quiet place for the names you want to follow.")
    selected = st.multiselect("Your list", data.Symbol.tolist(), default=["RELIANCE", "HDFCBANK", "INFY"])
    st.dataframe(data[data.Symbol.isin(selected)], use_container_width=True, hide_index=True)


def news():
    st.header("News")
    for title, source, time in [
        ("Market breadth improves as large caps lead the session", "Market desk", "Today"),
        ("Earnings calendar: what to watch this week", "Company filings", "Today"),
        ("Sector snapshot: financials and energy", "Market desk", "Yesterday"),
    ]:
        st.markdown(f"<div class='feed'><b>{title}</b><br><span class='small-note'>{source} · {time}</span></div>", unsafe_allow_html=True)


def mcp_lab():
    st.header("NSE MCP lab")
    st.write("Connect this Streamlit dashboard to NSE’s official public MCP endpoints. The response is shown raw so you can learn the tool contract before styling it into a screen.")
    source = st.radio("Official NSE source", ["CM market (current market data)", "Bhavcopy (historical EOD data)"], horizontal=True)
    endpoint = CM_MARKET_URL if source.startswith("CM market") else BHAVCOPY_URL
    st.code(endpoint, language="text")
    if st.button("Discover available NSE tools"):
        try:
            st.session_state["tools"] = list_tools(endpoint)
            st.session_state["tools_endpoint"] = endpoint
            st.success(f"Connected — found {len(st.session_state['tools'])} tools.")
        except Exception as error:
            st.error(f"Could not reach NSE MCP: {error}")
    tools = st.session_state.get("tools", []) if st.session_state.get("tools_endpoint") == endpoint else []
    if tools:
        tool = st.selectbox("Tool", tools)
        arguments = st.text_area("Arguments (JSON)", value="{}")
        if st.button("Run MCP tool"):
            import json
            try:
                st.json(call_nse_tool(tool, json.loads(arguments), endpoint))
            except Exception as error:
                st.error(f"MCP request failed: {error}")
    st.caption("The NSE server returns raw exchange data. Validate fields, cache responsibly, and keep this educational—not a trade-execution workflow.")


inject_css()
data = demo_universe()
with st.sidebar:
    st.markdown("<div class='brand'>Investor<b>Paisa</b></div><p class='small-note'>Streamlit recreation</p>", unsafe_allow_html=True)
    page = st.radio("Navigate", ["Dashboard", "Screener", "Charts", "Watchlist", "News", "NSE MCP lab"], label_visibility="collapsed")
    st.divider()
    st.markdown("<div class='eyebrow'>Data mode</div>", unsafe_allow_html=True)
    st.success("Demo snapshot ready")
    st.caption("Use NSE MCP lab to discover and call the live source.")

{"Dashboard": dashboard, "Screener": screener, "Charts": charts, "Watchlist": watchlist, "News": news, "NSE MCP lab": mcp_lab}[page](data) if page not in ("News", "NSE MCP lab") else {"News": news, "NSE MCP lab": mcp_lab}[page]()
