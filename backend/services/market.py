from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from backend.core.cache import cache
from backend.core.config import get_settings
from backend.data.nse_provider import fetch_constituents, fetch_history, fetch_nifty_200_quotes
from backend.db.database import SessionLocal
from backend.db.models import DailyBar, IndexMembership, Instrument, SectorDailyMetric, TechnicalSnapshot


def overview() -> dict:
    settings = get_settings()
    key = "market:overview:nifty200"
    if cached := cache.get(key):
        return cached
    rows = _persisted_overview_rows()
    source = "Persistent market store"
    if len(rows) < 200:
        constituents = fetch_constituents()
        rows = fetch_nifty_200_quotes(constituents)
        source = "NSE Indices + NSE Bhavcopy MCP (warm-up)"
    advances = sum(1 for row in rows if row.get("pct_change", 0) > 0)
    declines = sum(1 for row in rows if row.get("pct_change", 0) < 0)
    latest_date = rows[0].get("date") if rows else None
    response = {
        "index": "NIFTY200",
        "as_of": latest_date,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "is_stale": False,
        "universe_count": len(rows),
        "breadth": {"advances": advances, "declines": declines, "unchanged": len(rows) - advances - declines},
        "average_change_pct": round(sum(row.get("pct_change", 0) for row in rows) / len(rows), 2) if rows else 0,
        "constituents": rows,
    }
    cache.set(key, response, settings.cache_ttl_seconds)
    return response


def bars(symbol: str, range_key: str) -> dict:
    months_by_range = {"1D": 1, "1W": 1, "1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36}
    if range_key not in months_by_range:
        raise ValueError("Unsupported range")
    cache_key = f"bars:{symbol.upper()}:{range_key}"
    if cached := cache.get(cache_key):
        return cached
    rows = _persisted_bars(symbol)
    source = "Persistent market store"
    if not rows:
        rows = fetch_history(symbol, months_by_range[range_key])
        source = "NSE Bhavcopy MCP (warm-up)"
    else:
        rows = rows[-({"1D": 1, "1W": 5, "1M": 22, "3M": 66, "6M": 132, "1Y": 264, "3Y": 800}[range_key]):]
    if range_key == "1D":
        rows = rows[-1:]
    elif range_key == "1W":
        rows = rows[-5:]
    response = {"symbol": symbol.upper(), "range": range_key, "source": source, "as_of": rows[-1]["date"] if rows else None, "bars": rows}
    cache.set(cache_key, response, 3600)
    return response


def _persisted_overview_rows() -> list[dict]:
    with SessionLocal() as session:
        latest_date = session.scalar(select(func.max(DailyBar.trading_date)))
        if not latest_date:
            return []
        statement = (select(DailyBar, Instrument)
                     .join(Instrument, Instrument.id == DailyBar.instrument_id)
                     .join(IndexMembership, IndexMembership.instrument_id == Instrument.id)
                     .where(DailyBar.trading_date == latest_date, IndexMembership.index_code == "NIFTY200", IndexMembership.effective_to.is_(None)))
        rows = []
        for bar, instrument in session.execute(statement):
            previous = session.scalar(select(DailyBar.close).where(DailyBar.instrument_id == instrument.id, DailyBar.trading_date < latest_date).order_by(DailyBar.trading_date.desc()).limit(1))
            pct_change = round(((bar.close / previous) - 1) * 100, 2) if previous else 0.0
            rows.append({"symbol": instrument.symbol, "company": instrument.company_name, "industry": instrument.industry, "close": bar.close, "open": bar.open, "high": bar.high, "low": bar.low, "volume": bar.volume, "pct_change": pct_change, "date": latest_date.isoformat()})
        return rows


def _persisted_bars(symbol: str) -> list[dict]:
    with SessionLocal() as session:
        instrument = session.scalar(select(Instrument).where(Instrument.symbol == symbol.upper()))
        if not instrument:
            return []
        bars = session.scalars(select(DailyBar).where(DailyBar.instrument_id == instrument.id).order_by(DailyBar.trading_date)).all()
        return [{"date": bar.trading_date.isoformat(), "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close, "ltp": bar.close, "volume": bar.volume} for bar in bars]


def sectors() -> dict:
    with SessionLocal() as session:
        latest_date = session.scalar(select(func.max(SectorDailyMetric.trading_date)))
        if not latest_date:
            return {"as_of": None, "sectors": []}
        rows = session.scalars(select(SectorDailyMetric).where(SectorDailyMetric.trading_date == latest_date, SectorDailyMetric.index_code == "NIFTY200").order_by(SectorDailyMetric.average_change_pct.desc())).all()
        return {"as_of": latest_date.isoformat(), "sectors": [{"industry": row.industry, "members": row.members, "advancers": row.advancers, "decliners": row.decliners, "average_change_pct": row.average_change_pct, "turnover": row.turnover} for row in rows]}


def screen(
    industry: str | None = None,
    min_rsi: float | None = None,
    min_volume_ratio: float | None = None,
    above_sma50: bool | None = None,
    min_return_1m: float | None = None,
    above_sma200: bool | None = None,
    min_return_3m: float | None = None,
    min_rel_strength_6m: float | None = None,
    near_52w_high_pct: float | None = None,
    new_52w_high: bool | None = None,
    volume_spike: bool | None = None,
    golden_cross: bool | None = None,
    limit: int = 200,
) -> dict:
    with SessionLocal() as session:
        latest_date = session.scalar(select(func.max(TechnicalSnapshot.trading_date)))
        if not latest_date:
            return {"as_of": None, "total": 0, "matches": []}
        statement = (select(Instrument, DailyBar, TechnicalSnapshot)
                     .join(DailyBar, DailyBar.instrument_id == Instrument.id)
                     .join(TechnicalSnapshot, TechnicalSnapshot.instrument_id == Instrument.id)
                     .join(IndexMembership, IndexMembership.instrument_id == Instrument.id)
                     .where(DailyBar.trading_date == latest_date, TechnicalSnapshot.trading_date == latest_date, IndexMembership.index_code == "NIFTY200", IndexMembership.effective_to.is_(None)))
        if industry:
            statement = statement.where(Instrument.industry == industry)
        if min_rsi is not None:
            statement = statement.where(TechnicalSnapshot.rsi14 >= min_rsi)
        if min_volume_ratio is not None:
            statement = statement.where(TechnicalSnapshot.volume_ratio_20d >= min_volume_ratio)
        if min_return_1m is not None:
            statement = statement.where(TechnicalSnapshot.return_1m >= min_return_1m)
        if above_sma50:
            statement = statement.where(DailyBar.close > TechnicalSnapshot.sma50)
        if above_sma200:
            statement = statement.where(DailyBar.close > TechnicalSnapshot.sma200)
        if min_return_3m is not None:
            statement = statement.where(TechnicalSnapshot.return_3m >= min_return_3m)
        if min_rel_strength_6m is not None:
            statement = statement.where(TechnicalSnapshot.rel_strength_6m >= min_rel_strength_6m)
        if near_52w_high_pct is not None:
            statement = statement.where(TechnicalSnapshot.distance_high_52w >= -abs(near_52w_high_pct))
        if new_52w_high:
            statement = statement.where(TechnicalSnapshot.new_52w_high.is_(True))
        if volume_spike:
            statement = statement.where(TechnicalSnapshot.volume_ratio_20d >= 2)
        if golden_cross:
            statement = statement.where(TechnicalSnapshot.golden_cross_20d.is_(True))
        rows = session.execute(statement.order_by(TechnicalSnapshot.return_1m.desc().nullslast()).limit(min(limit, 200))).all()
        total_universe = session.scalar(
            select(func.count())
            .select_from(IndexMembership)
            .where(IndexMembership.index_code == "NIFTY200", IndexMembership.effective_to.is_(None))
        ) or 0
        coverage = session.scalar(
            select(func.count())
            .select_from(TechnicalSnapshot)
            .join(IndexMembership, IndexMembership.instrument_id == TechnicalSnapshot.instrument_id)
            .where(TechnicalSnapshot.trading_date == latest_date, IndexMembership.index_code == "NIFTY200", IndexMembership.effective_to.is_(None))
        ) or 0
        matches = [{
            "symbol": instrument.symbol, "company": instrument.company_name, "industry": instrument.industry,
            "close": bar.close, "rsi14": technical.rsi14, "sma20": technical.sma20,
            "sma50": technical.sma50, "sma200": technical.sma200,
            "above_ma_count": technical.above_ma_count, "atr14_pct": technical.atr14_pct,
            "vol1y": technical.vol1y, "maxdd1y": technical.maxdd1y,
            "beta_equal_weight": technical.beta_equal_weight, "rel_strength_6m": technical.rel_strength_6m,
            "volume_ratio_20d": technical.volume_ratio_20d, "volume_spikes_20d": technical.volume_spikes_20d,
            "return_1d": technical.return_1d, "return_1w": technical.return_1w,
            "return_1m": technical.return_1m, "return_3m": technical.return_3m,
            "return_6m": technical.return_6m, "return_1y": technical.return_1y,
            "return_3y_cagr": technical.return_3y_cagr, "distance_high_52w": technical.distance_high_52w,
            "position_52w": technical.position_52w, "new_52w_high": technical.new_52w_high,
            "golden_cross_20d": technical.golden_cross_20d,
        } for instrument, bar, technical in rows]
        return {"as_of": latest_date.isoformat(), "total": len(matches), "universe_count": total_universe, "technical_coverage": coverage, "matches": matches}
