"""Idempotent Nifty 200 reference, bar, and technical-data ingestion."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.data.nse_provider import fetch_constituents, fetch_history, fetch_nifty_200_quotes
from backend.core.cache import cache
from backend.db.models import DailyBar, IndexMembership, IngestionRun, Instrument, SectorDailyMetric, TechnicalSnapshot

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
    frame = pd.DataFrame([{"date": item.trading_date, "open": item.open, "high": item.high, "low": item.low, "close": item.close, "volume": item.volume, "turnover": item.turnover or item.close * item.volume} for item in bars])
    latest = frame.iloc[-1]
    snapshot = session.scalar(select(TechnicalSnapshot).where(TechnicalSnapshot.instrument_id == instrument.id, TechnicalSnapshot.trading_date == latest.date))
    values = _technical_values(frame)
    if snapshot:
        for field, value in values.items():
            setattr(snapshot, field, value)
    else:
        session.add(TechnicalSnapshot(instrument_id=instrument.id, trading_date=latest.date, **values))
    session.commit()
    return {"symbol": symbol, "as_of": latest.date.isoformat(), **values}


def calculate_universe_technicals(session: Session) -> dict:
    """Compute cross-sectional indicators after all constituent histories are available."""
    instruments = session.scalars(select(Instrument).where(Instrument.active.is_(True))).all()
    frames: dict[int, pd.DataFrame] = {}
    for instrument in instruments:
        bars = session.scalars(select(DailyBar).where(DailyBar.instrument_id == instrument.id).order_by(DailyBar.trading_date)).all()
        if bars:
            frames[instrument.id] = pd.DataFrame([{"date": bar.trading_date, "close": bar.close} for bar in bars]).set_index("date")
    if not frames:
        return {"updated": 0}
    closes = pd.concat({instrument_id: frame["close"] for instrument_id, frame in frames.items()}, axis=1).sort_index()
    equal_weight_returns = closes.pct_change().mean(axis=1)
    updated = 0
    for instrument in instruments:
        frame = frames.get(instrument.id)
        if frame is None:
            continue
        stock_returns = frame["close"].pct_change()
        aligned = pd.concat([stock_returns, equal_weight_returns], axis=1).dropna().tail(252)
        beta = None
        if len(aligned) > 20 and aligned.iloc[:, 1].var() != 0:
            beta = _value(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]) / aligned.iloc[:, 1].var())
        six_month_return = _return(frame["close"], 126)
        peers = closes.pct_change(126).iloc[-1].dropna()
        rs_rank = float(peers.rank(pct=True).get(instrument.id, float("nan")) * 100) if not peers.empty else float("nan")
        latest_date = frame.index[-1]
        snapshot = session.scalar(select(TechnicalSnapshot).where(TechnicalSnapshot.instrument_id == instrument.id, TechnicalSnapshot.trading_date == latest_date))
        if snapshot:
            snapshot.beta_equal_weight = beta
            snapshot.rel_strength_6m = _value(rs_rank)
            updated += 1
    session.commit()
    return {"updated": updated}


def calculate_sector_metrics(session: Session, trading_date: date | None = None) -> int:
    """Persist equal-weighted sector breadth and turnover for the active universe."""
    as_of = trading_date or session.scalar(select(DailyBar.trading_date).order_by(DailyBar.trading_date.desc()).limit(1))
    if not as_of:
        return 0
    statement = (select(DailyBar, Instrument)
                 .join(Instrument, Instrument.id == DailyBar.instrument_id)
                 .join(IndexMembership, IndexMembership.instrument_id == Instrument.id)
                 .where(DailyBar.trading_date == as_of, IndexMembership.index_code == INDEX_CODE, IndexMembership.effective_to.is_(None)))
    rows = list(session.execute(statement))
    grouped: dict[str, list[tuple[DailyBar, Instrument]]] = {}
    for bar, instrument in rows:
        grouped.setdefault(instrument.industry or "Unclassified", []).append((bar, instrument))
    for industry, sector_rows in grouped.items():
        changes, turnover = [], 0.0
        for bar, instrument in sector_rows:
            previous = session.scalar(select(DailyBar.close).where(DailyBar.instrument_id == instrument.id, DailyBar.trading_date < as_of).order_by(DailyBar.trading_date.desc()).limit(1))
            change = ((bar.close / previous) - 1) * 100 if previous else 0.0
            changes.append(change)
            turnover += bar.turnover if bar.turnover is not None else bar.close * bar.volume
        metric = session.scalar(select(SectorDailyMetric).where(SectorDailyMetric.index_code == INDEX_CODE, SectorDailyMetric.industry == industry, SectorDailyMetric.trading_date == as_of))
        values = {"members": len(sector_rows), "advancers": sum(change > 0 for change in changes), "decliners": sum(change < 0 for change in changes), "average_change_pct": round(sum(changes) / len(changes), 4), "turnover": turnover}
        if metric:
            for field, value in values.items():
                setattr(metric, field, value)
        else:
            session.add(SectorDailyMetric(index_code=INDEX_CODE, industry=industry, trading_date=as_of, **values))
    session.commit()
    return len(grouped)


def _value(value: float) -> float | None:
    return None if pd.isna(value) else round(float(value), 4)


def _ratio(value: float, average: float) -> float | None:
    return None if pd.isna(average) or not average else round(float(value / average), 4)


def _return(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods:
        return None
    return round(float((close.iloc[-1] / close.iloc[-periods - 1] - 1) * 100), 4)


def _technical_values(frame: pd.DataFrame) -> dict:
    close, high, low, volume, turnover = frame["close"], frame["high"], frame["low"], frame["volume"], frame["turnover"]
    sma = {window: close.rolling(window).mean() for window in (20, 50, 100, 200)}
    ema = {window: close.ewm(span=window, adjust=False).mean() for window in (20, 50, 100, 200)}
    delta = close.diff()
    gains, losses = delta.clip(lower=0), -delta.clip(upper=0)
    average_gain, average_loss = gains.rolling(14).mean(), losses.rolling(14).mean()
    relative_strength = average_gain / average_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + relative_strength))
    rsi = rsi.mask((average_loss == 0) & (average_gain > 0), 100).mask((average_gain == 0) & (average_loss > 0), 0)
    previous_close = close.shift(1)
    true_range = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
    atr = true_range.rolling(14).mean()
    high52, low52 = high.rolling(252).max(), low.rolling(252).min()
    latest_close = close.iloc[-1]
    distances = {window: _value((latest_close / series.iloc[-1] - 1) * 100) if not pd.isna(series.iloc[-1]) else None for window, series in sma.items()}
    ma_gap = sma[50] - sma[200]
    golden = bool(((ma_gap > 0) & (ma_gap.shift(1) <= 0)).tail(20).any()) if len(close) >= 201 else False
    death = bool(((ma_gap < 0) & (ma_gap.shift(1) >= 0)).tail(20).any()) if len(close) >= 201 else False
    max_drawdown = ((close.tail(252) / close.tail(252).cummax()) - 1).min() * 100 if len(close) >= 2 else float("nan")
    return {
        "sma20": _value(sma[20].iloc[-1]), "sma50": _value(sma[50].iloc[-1]), "sma100": _value(sma[100].iloc[-1]), "sma200": _value(sma[200].iloc[-1]),
        "ema20": _value(ema[20].iloc[-1]), "ema50": _value(ema[50].iloc[-1]), "ema100": _value(ema[100].iloc[-1]), "ema200": _value(ema[200].iloc[-1]),
        "d20": distances[20], "d50": distances[50], "d100": distances[100], "d200": distances[200],
        "above_ma_count": sum(value is not None and value > 0 for value in distances.values()), "rsi14": _value(rsi.iloc[-1]),
        "atr14_pct": _value(atr.iloc[-1] / latest_close * 100), "vol1y": _value(close.pct_change().tail(252).std() * (252 ** 0.5) * 100), "maxdd1y": _value(max_drawdown),
        "return_1d": _return(close, 1), "return_1w": _return(close, 5), "return_1m": _return(close, 21), "return_3m": _return(close, 63), "return_6m": _return(close, 126), "return_1y": _return(close, 252),
        "return_3y_cagr": _value(((latest_close / close.iloc[-757]) ** (1 / 3) - 1) * 100) if len(close) > 756 else None,
        "volume_ratio_20d": _ratio(volume.iloc[-1], volume.rolling(20).mean().iloc[-1]), "avg_volume_20d": _value(volume.rolling(20).mean().iloc[-1]), "avg_turnover_20d": _value(turnover.rolling(20).mean().iloc[-1]), "volume_spikes_20d": int((volume.tail(20) > volume.rolling(20).mean().tail(20) * 2).sum()) if len(volume) >= 20 else 0,
        "high_52w": _value(high52.iloc[-1]), "low_52w": _value(low52.iloc[-1]), "distance_high_52w": _value((latest_close / high52.iloc[-1] - 1) * 100) if not pd.isna(high52.iloc[-1]) else None, "distance_low_52w": _value((latest_close / low52.iloc[-1] - 1) * 100) if not pd.isna(low52.iloc[-1]) else None,
        "position_52w": _value((latest_close - low52.iloc[-1]) / (high52.iloc[-1] - low52.iloc[-1]) * 100) if not pd.isna(high52.iloc[-1]) and high52.iloc[-1] != low52.iloc[-1] else None,
        "new_52w_high": bool(latest_close >= high52.iloc[-1]) if not pd.isna(high52.iloc[-1]) else False, "new_52w_low": bool(latest_close <= low52.iloc[-1]) if not pd.isna(low52.iloc[-1]) else False,
        "golden_cross_20d": golden, "death_cross_20d": death,
    }
