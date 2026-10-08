from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st
import altair as alt

from streamlit_data import fetch_constituents, fetch_history, fetch_quotes
from chart_technicals import add_technicals, technical_summary
from refresh_control import RefreshGate

st.set_page_config(page_title="paisaan · CapitalSense Advisors", page_icon="₹", layout="wide")

ACCENT, GREEN, RED, MUTED = "#2bd4a4", "#2bd4a4", "#ff6b6b", "#8d98a7"


def safe_text(value: object) -> str:
    return escape(str(value))


@st.cache_resource
def refresh_gate() -> RefreshGate:
    """Share explicit-refresh protection across users on this app instance."""
    return RefreshGate(cooldown_seconds=60)


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


def screened_stocks(data: pd.DataFrame, industry: str | None, min_change: float | None, min_volume: int | None) -> pd.DataFrame:
    """Fast, full-universe screen on cached EOD fields available in Streamlit."""
    result = data.copy()
    if industry:
        result = result[result["Industry"] == industry]
    if min_change is not None:
        result = result[result["Change %"] >= min_change]
    if min_volume is not None:
        result = result[result["Volume"] >= min_volume]
    return result.sort_values("Change %", ascending=False)


RANGES = {"1D": 1, "1W": 1, "1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36}


@st.cache_data(ttl=3600, show_spinner="Loading historical NSE bhavcopy data…")
def stock_history(symbol: str, months_needed: int) -> pd.DataFrame:
    """Read one chart directly from NSE MCP; cache keeps navigation fast."""
    history = pd.DataFrame(fetch_history(symbol, months_needed)).drop_duplicates(subset="date").sort_values("date")
    if history.empty:
        raise RuntimeError(f"No Bhavcopy history is available for {symbol}.")
    if "close" not in history and "ltp" in history:
        history = history.rename(columns={"ltp": "close"})
    if "volume" not in history and "totalTradedVolume" in history:
        history = history.rename(columns={"totalTradedVolume": "volume"})
    history["date"] = pd.to_datetime(history["date"])
    return history


def display_chart(history: pd.DataFrame, candle: bool, long_range: bool = False):
    """Fast Vega-Lite market chart; older history is downsampled before render."""
    view = history.copy()
    if long_range and len(view) > 260:
        aggregation = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        aggregation.update({column: "last" for column in ("sma20", "sma50", "sma200") if column in view})
        view = view.set_index("date").resample("W-FRI").agg(aggregation).dropna(subset=["open", "high", "low", "close"]).reset_index()
    base = alt.Chart(view).encode(x=alt.X("date:T", title=None, axis=alt.Axis(grid=False, labelColor=MUTED)), tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip("open:Q", title="Open", format=".2f"), alt.Tooltip("high:Q", title="High", format=".2f"), alt.Tooltip("low:Q", title="Low", format=".2f"), alt.Tooltip("close:Q", title="Close", format=".2f")])
    if candle:
        color = alt.condition("datum.open <= datum.close", alt.value(GREEN), alt.value(RED))
        chart = base.mark_rule().encode(y=alt.Y("low:Q", title=None, scale=alt.Scale(zero=False), axis=alt.Axis(gridColor="#202932", labelColor=MUTED)), y2="high:Q", color=color) + base.mark_bar(size=7).encode(y=alt.Y("open:Q", scale=alt.Scale(zero=False)), y2="close:Q", color=color)
    else:
        chart = base.mark_area(line={"color": ACCENT, "strokeWidth": 2.5}, color=alt.Gradient(gradient="linear", stops=[alt.GradientStop(color="rgba(43,212,164,.22)", offset=0), alt.GradientStop(color="rgba(43,212,164,0)", offset=1)], x1=1, x2=1, y1=1, y2=0)).encode(y=alt.Y("close:Q", title=None, axis=alt.Axis(gridColor="#202932", labelColor=MUTED)))
    for column, color in (("sma20", "#ffd166"), ("sma50", "#8ab4ff"), ("sma200", "#d0a2ff")):
        if column in view and view[column].notna().any():
            chart += base.mark_line(color=color, strokeWidth=1.4, opacity=.9).encode(y=alt.Y(f"{column}:Q", title=None))
    return chart.properties(height=315).resolve_scale(y="shared").configure_view(strokeOpacity=0).configure_axis(domain=False, tickColor="#202932")


def gain(value: float) -> str:
    return f"<span class='{ 'gain' if value >= 0 else 'loss' }'>{value:+.2f}%</span>"


def mover_row(row: pd.Series) -> None:
    strength = min(abs(row["Change %"]) / 8 * 100, 100)
    color = GREEN if row["Change %"] >= 0 else RED
    st.markdown(f"<div class='feed'><b>{safe_text(row['Symbol'])}</b><span style='float:right'>{gain(row['Change %'])}</span><br><span class='small-note'>{safe_text(row['Company'])} · ₹{row['Price']:,.2f}</span><div class='move-bar'><div class='move-fill' style='width:{strength:.0f}%;background:{color}'></div></div></div>", unsafe_allow_html=True)


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
        symbol = st.selectbox("Chart symbol", data.Symbol.tolist(), index=0, label_visibility="collapsed")
        try:
            history = stock_history(symbol, 3)
            st.markdown(f"<div class='panel-title'>{safe_text(symbol)}</div><div class='panel-subtitle'>3-month Bhavcopy close</div>", unsafe_allow_html=True)
            st.altair_chart(display_chart(history, candle=False), use_container_width=True)
        except Exception:
            st.warning("This chart is temporarily unavailable. The rest of the market snapshot is still current.")
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


def screener(data: pd.DataFrame):
    st.header("Screener")
    st.caption("No FOMO filters—just a fast, full-universe EOD screen. Historical technical filters need persistent infrastructure, so they are intentionally not represented as current data here.")
    x, y, z = st.columns(3)
    industry = x.selectbox("Industry", ["All"] + sorted(data.Industry.dropna().unique().tolist()))
    min_change = y.number_input("Minimum daily change (%)", value=0.0, step=0.25)
    min_volume = z.number_input("Minimum traded volume", min_value=0, value=0, step=100_000)
    result = screened_stocks(data, industry if industry != "All" else None, min_change if min_change != 0 else None, min_volume if min_volume > 0 else None)
    st.caption(f"Coverage: {len(data)} / 200 verified constituents · EOD snapshot date: {data['date'].iloc[0]}")
    if result.empty:
        st.info("No Nifty 200 stocks match these filters.")
        return
    shown = result[["Symbol", "Company", "Industry", "Price", "Change %", "Volume", "Day High", "Day Low"]]
    st.dataframe(shown, use_container_width=True, hide_index=True)
    st.caption(f"{len(result)} matches")


def charts(data: pd.DataFrame):
    st.markdown("<div class='chart-heading'>Charts</div><div class='chart-meta'>Meme energy, terminal discipline · live NSE snapshot with historical Bhavcopy data</div>", unsafe_allow_html=True)
    symbol_col, range_col = st.columns([1.25, 3.75], vertical_alignment="bottom")
    symbol = symbol_col.selectbox("Symbol", data.Symbol.tolist())
    range_label = range_col.radio("Range", list(RANGES), horizontal=True, index=2)
    row = data.set_index("Symbol").loc[symbol]
    st.markdown(f"<div class='chart-heading' style='font-size:1.42rem;margin-top:.25rem'>{symbol} &nbsp; ₹{row.Price:,.2f} &nbsp; {gain(row['Change %'])}</div>", unsafe_allow_html=True)
    try:
        history = add_technicals(stock_history(symbol, RANGES[range_label]))
    except Exception:
        st.error("Historical chart data is temporarily unavailable. Try again shortly.")
        return
    metrics = technical_summary(history)
    metric_columns = st.columns(5)
    metric_columns[0].metric("RSI-14", f"{metrics['rsi14']:.1f}" if metrics["rsi14"] is not None else "—")
    metric_columns[1].metric("SMA-20", f"₹{metrics['sma20']:,.2f}" if metrics["sma20"] is not None else "—")
    metric_columns[2].metric("SMA-50", f"₹{metrics['sma50']:,.2f}" if metrics["sma50"] is not None else "—")
    metric_columns[3].metric("SMA-200", f"₹{metrics['sma200']:,.2f}" if metrics["sma200"] is not None else "—")
    metric_columns[4].metric("1-month return", f"{metrics['return_1m']:+.2f}%" if metrics["return_1m"] is not None else "—")
    if range_label == "1D":
        history = history.tail(1)
    elif range_label == "1W":
        history = history.tail(5)
    st.altair_chart(display_chart(history, candle=range_label in {"1D", "1W", "1M"}, long_range=range_label in {"1Y", "3Y"}), use_container_width=True)
    st.caption(f"{len(history)} NSE Bhavcopy observations · {history.date.min():%d %b %Y} to {history.date.max():%d %b %Y}")


inject_css()
try:
    data, updated = live_universe()
except Exception as error:
    st.error(f"NSE data could not be loaded: {error}")
    if st.button("Try NSE data again"):
        live_universe.clear()
        st.rerun()
    st.stop()
with st.sidebar:
    st.markdown("<div class='brand'>pai<b>saan</b></div><p class='small-note'>CapitalSense Advisors</p>", unsafe_allow_html=True)
    page = st.radio("Navigate", ["Dashboard", "Screener", "Charts"], label_visibility="collapsed")
    st.divider()
    st.markdown("<div class='eyebrow'>Data mode</div>", unsafe_allow_html=True)
    if st.button("Refresh NSE data", use_container_width=True):
        allowed, remaining = refresh_gate().request()
        if allowed:
            live_universe.clear()
            stock_history.clear()
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
