"""Idempotent Nifty 200 reference, bar, and technical-data ingestion."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.data.nse_provider import fetch_constituents, fetch_history, fetch_nifty_200_quotes
from backend.core.cache import cache
from backend.db.models import DailyBar, IndexMembership, IngestionRun, Instrument, TechnicalSnapshot

INDEX_CODE = "NIFTY200"


def _source_hash(items: list[dict]) -> str:
    symbols = ",".join(sorted(item["symbol"] for item in items if item.get("symbol")))
    return hashlib.sha256(symbols.encode()).hexdigest()


def _quote_date(quote: dict) -> date:
    return datetime.strptime(quote["date"], "%Y-%m-%d").date()


def _upsert_bar(session: Session, instrument_id: int, row: dict) -> None:
    trading_date = _quote_date(row) if "date" in row else datetime.strptime(row["trading_date"], "%Y-%m-%d").date()
    existing = session.scalar(select(DailyBar).where(DailyBar.instrument_id == instrument_id, DailyBar.trading_date == trading_date))
    payload = {
        "open": float(row["open"]), "high": float(row["high"]), "low": float(row["low"]),
        "close": float(row.get("close", row.get("ltp"))), "volume": int(row.get("volume", 0)),
        "turnover": float(row.get("totalTradedValue")) if row.get("totalTradedValue") is not None else None,
    }
    if existing:
        for field, value in payload.items():
            setattr(existing, field, value)
    else:
        session.add(DailyBar(instrument_id=instrument_id, trading_date=trading_date, **payload))


def ingest_nifty_200_eod(session: Session) -> dict:
    """Refresh membership and one EOD bar per official constituent."""
    run = IngestionRun(job_name="nifty_200_eod", status="running")
    session.add(run)
    session.flush()
    try:
        constituents = fetch_constituents()
        quotes = fetch_nifty_200_quotes(constituents)
        as_of = _quote_date(quotes[0])
        source_hash = _source_hash(constituents)
        symbols = {item["symbol"] for item in constituents}
        existing = {item.symbol: item for item in session.scalars(select(Instrument).where(Instrument.symbol.in_(symbols))).all()}
        instruments: dict[str, Instrument] = {}
        for item in constituents:
            instrument = existing.get(item["symbol"])
            if not instrument:
                instrument = Instrument(symbol=item["symbol"], isin=item.get("isin"), company_name=item.get("company", item["symbol"]), industry=item.get("industry"))
                session.add(instrument)
                session.flush()
            else:
                instrument.isin, instrument.company_name, instrument.industry, instrument.active = item.get("isin"), item.get("company", instrument.company_name), item.get("industry"), True
            instruments[item["symbol"]] = instrument

        active_memberships = session.scalars(select(IndexMembership).where(IndexMembership.index_code == INDEX_CODE, IndexMembership.effective_to.is_(None))).all()
        active_symbols = {session.get(Instrument, membership.instrument_id).symbol: membership for membership in active_memberships}
        for symbol, membership in active_symbols.items():
            if symbol not in symbols:
                membership.effective_to = as_of - timedelta(days=1)
        for symbol, instrument in instruments.items():
            if symbol not in active_symbols:
                session.add(IndexMembership(index_code=INDEX_CODE, instrument_id=instrument.id, effective_from=as_of, source_hash=source_hash))

        for quote in quotes:
            _upsert_bar(session, instruments[quote["symbol"]].id, quote)
        run.status, run.row_count, run.completed_at = "completed", len(quotes), datetime.utcnow()
        session.commit()
        cache.delete("market:overview:nifty200")
        return {"as_of": as_of.isoformat(), "members": len(constituents), "bars": len(quotes), "run_id": run.id}
    except Exception as error:
        session.rollback()
        failed = IngestionRun(job_name="nifty_200_eod", status="failed", completed_at=datetime.utcnow(), error=str(error))
        session.add(failed)
        session.commit()
        raise


def backfill_history(session: Session, symbol: str, months: int = 36) -> int:
    instrument = session.scalar(select(Instrument).where(Instrument.symbol == symbol.upper()))
    if not instrument:
        raise ValueError(f"Unknown instrument: {symbol}")
    rows = fetch_history(symbol, months)
    for row in rows:
        _upsert_bar(session, instrument.id, row)
    session.commit()
    for range_key in ("1D", "1W", "1M", "3M", "6M", "1Y", "3Y"):
        cache.delete(f"bars:{symbol.upper()}:{range_key}")
    return len(rows)


def calculate_latest_technicals(session: Session, symbol: str) -> dict:
    instrument = session.scalar(select(Instrument).where(Instrument.symbol == symbol.upper()))
    if not instrument:
        raise ValueError(f"Unknown instrument: {symbol}")
    bars = session.scalars(select(DailyBar).where(DailyBar.instrument_id == instrument.id).order_by(DailyBar.trading_date)).all()
    if not bars:
        return {"symbol": symbol, "status": "no_bars"}
    frame = pd.DataFrame([{"date": item.trading_date, "close": item.close, "volume": item.volume} for item in bars])
    close, volume = frame["close"], frame["volume"]
    delta = close.diff()
    gains, losses = delta.clip(lower=0), -delta.clip(upper=0)
    average_gain, average_loss = gains.rolling(14).mean(), losses.rolling(14).mean()
    rsi = 100 - (100 / (1 + average_gain / average_loss.replace(0, float("nan"))))
    latest = frame.iloc[-1]
    snapshot = session.scalar(select(TechnicalSnapshot).where(TechnicalSnapshot.instrument_id == instrument.id, TechnicalSnapshot.trading_date == latest.date))
    values = {
        "sma50": _value(close.rolling(50).mean().iloc[-1]), "sma200": _value(close.rolling(200).mean().iloc[-1]),
        "rsi14": _value(rsi.iloc[-1]), "volume_ratio_20d": _ratio(volume.iloc[-1], volume.rolling(20).mean().iloc[-1]),
        "return_1m": _return(close, 21), "return_1y": _return(close, 252),
    }
    if snapshot:
        for field, value in values.items():
            setattr(snapshot, field, value)
    else:
        session.add(TechnicalSnapshot(instrument_id=instrument.id, trading_date=latest.date, **values))
    session.commit()
    return {"symbol": symbol, "as_of": latest.date.isoformat(), **values}


def _value(value: float) -> float | None:
    return None if pd.isna(value) else round(float(value), 4)


def _ratio(value: float, average: float) -> float | None:
    return None if pd.isna(average) or not average else round(float(value / average), 4)


def _return(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods:
        return None
    return round(float((close.iloc[-1] / close.iloc[-periods - 1] - 1) * 100), 4)
