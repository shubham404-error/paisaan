from __future__ import annotations

from html import escape
import json
import os

import pandas as pd
import streamlit as st

from gemini_screener import DEFAULT_MODEL, GeminiScreenerError, build_chart_research_cues, build_research_shortlist, compare_research_stocks, translate_screener_request
from streamlit_data import fetch_constituents, fetch_quotes
from refresh_control import RefreshGate
from screener_service import FIELD_LABELS, fetch_yahoo_fundamentals, filter_fundamentals, parse_fundamental_query
from yahoo_chart_service import ADJUSTMENT_CONTRACT, OVERLAYS, YahooChartError, calculate_indicators, download_daily_history, load_with_last_valid, market_chart, yahoo_symbol

st.set_page_config(page_title="paisaan · CapitalSense Advisors", page_icon="₹", layout="wide")

ACCENT, GREEN, RED, MUTED = "#2bd4a4", "#2bd4a4", "#ff6b6b", "#8d98a7"


def safe_text(value: object) -> str:
    return escape(str(value))


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
      .screener-hero { padding:1.35rem 1.5rem; margin-bottom:1rem; border:1px solid #263b3a; border-radius:18px; background:linear-gradient(115deg, rgba(17,36,35,.92), rgba(14,20,29,.9)); }
      .screener-hero h1 { margin:.15rem 0 .3rem; font-size:2rem; letter-spacing:-.055em; }
      .screener-kicker { color:#2bd4a4; font-size:.72rem; letter-spacing:.14em; text-transform:uppercase; }
      .scan-summary { padding:.7rem .85rem; border:1px solid #26313d; border-radius:12px; background:rgba(16,22,29,.72); color:#b9c3ce; font-size:.82rem; }
      .scan-summary b { color:#f0f4f8; }
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
        context_id = str(abs(hash((as_of, preset, rank_by, tuple(item["Symbol"] for item in facts["ranked_results"])))))
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
            render_research_list("Confirmation checks", cues["confirmation_checks"])
            render_research_list("Limitations", cues["limitations"])


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
        resolved_symbol = yahoo_symbol(symbol)
        cache_key = f"dashboard_yahoo_chart:{resolved_symbol}:3y:1d:{ADJUSTMENT_CONTRACT}"
        try:
            history, stale = load_with_last_valid(lambda: yahoo_chart_history(resolved_symbol, "3y", "1d", ADJUSTMENT_CONTRACT), st.session_state.get(cache_key))
            st.session_state[cache_key] = history
            st.markdown(f"<div class='panel-title'>{safe_text(symbol)}</div><div class='panel-subtitle'>3-month Yahoo Finance daily technical view</div>", unsafe_allow_html=True)
            st.plotly_chart(market_chart(history, resolved_symbol, ["EMA9", "EMA21", "SMA50"], days=66, rsi_lines=[(30, "RSI 30"), (70, "RSI 70")], height=460), use_container_width=True, config={"displaylogo": False, "scrollZoom": True})
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
    st.markdown("<section class='screener-hero'><div class='screener-kicker'>Nifty 200 EOD market scanner</div><h1>Find the move. Keep the context.</h1><div class='small-note'>Start with verified NSE data. Add Yahoo fundamentals only when you need a deeper custom screen.</div></section>", unsafe_allow_html=True)
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
    research_workbench(result, str(data["date"].iloc[0]), preset_copy, sort_label)
    inspect_col, action_col = st.columns([3, 1], vertical_alignment="bottom")
    inspect_symbol = inspect_col.selectbox("Inspect a result in Charts", result["Symbol"].tolist(), key="screener_inspect_symbol")

    action_col.button("Open chart", use_container_width=True, on_click=open_chart_for, args=(inspect_symbol,))
    st.caption("NSE fields use the latest cached Bhavcopy. Yahoo fundamentals are provider-reported and may be missing or delayed. This is a descriptive screen, not investment advice.")


def charts(data: pd.DataFrame):
    st.markdown("<div class='chart-heading'>Charts</div><div class='chart-meta'>Daily technical chart · Yahoo Finance adjusted OHLC · end-of-day data, not a live execution feed</div>", unsafe_allow_html=True)
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
    chart_research_cues(history, symbol, range_label)
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
with st.sidebar:
    st.markdown("<div class='brand'>pai<b>saan</b></div><p class='small-note'>CapitalSense Advisors</p>", unsafe_allow_html=True)
    page = st.radio("Navigate", ["Dashboard", "Screener", "Charts"], label_visibility="collapsed", key="page")
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
