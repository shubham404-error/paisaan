"""Scheduled jobs. Wire Celery Beat/cloud scheduler to these task names."""
from backend.worker.celery_app import celery_app
from backend.db.database import SessionLocal
from backend.db.models import Instrument
from backend.services.ingestion import backfill_history, calculate_latest_technicals, ingest_nifty_200_eod
from sqlalchemy import select


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def ingest_nifty_200_market_close() -> dict:
    with SessionLocal() as session:
        result = ingest_nifty_200_eod(session)
        symbols = session.scalars(select(Instrument.symbol)).all()
    for symbol in symbols:
        calculate_symbol_technicals.delay(symbol)
    return result


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def backfill_symbol(symbol: str, months: int = 36) -> dict:
    with SessionLocal() as session:
        rows = backfill_history(session, symbol, months)
        metrics = calculate_latest_technicals(session, symbol)
    return {"symbol": symbol, "bars": rows, "technicals": metrics}


@celery_app.task
def enqueue_initial_backfill(months: int = 36) -> dict:
    """Fan out historical loads after a successful reference/EOD ingestion."""
    with SessionLocal() as session:
        symbols = session.scalars(select(Instrument.symbol).where(Instrument.active.is_(True))).all()
    for symbol in symbols:
        backfill_symbol.delay(symbol, months)
    return {"queued": len(symbols), "months": months}


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def calculate_symbol_technicals(symbol: str) -> dict:
    with SessionLocal() as session:
        return calculate_latest_technicals(session, symbol)
