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


def screen(industry: str | None = None, min_rsi: float | None = None, min_volume_ratio: float | None = None, above_sma50: bool | None = None, min_return_1m: float | None = None, limit: int = 200) -> dict:
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
        rows = session.execute(statement.order_by(TechnicalSnapshot.return_1m.desc().nullslast()).limit(min(limit, 200))).all()
        matches = [{"symbol": instrument.symbol, "company": instrument.company_name, "industry": instrument.industry, "close": bar.close, "rsi14": technical.rsi14, "sma50": technical.sma50, "sma200": technical.sma200, "volume_ratio_20d": technical.volume_ratio_20d, "return_1m": technical.return_1m, "return_1y": technical.return_1y} for instrument, bar, technical in rows]
        return {"as_of": latest_date.isoformat(), "total": len(matches), "matches": matches}
