"""Scheduled jobs. Wire Celery Beat/cloud scheduler to these task names."""
from celery import chord
from backend.worker.celery_app import celery_app
from backend.db.database import SessionLocal
from backend.db.models import Instrument
from backend.services.ingestion import backfill_history, calculate_latest_technicals, calculate_sector_metrics, calculate_universe_technicals, ingest_nifty_200_eod
from sqlalchemy import select


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def ingest_nifty_200_market_close() -> dict:
    with SessionLocal() as session:
        result = ingest_nifty_200_eod(session)
        result["sectors"] = calculate_sector_metrics(session)
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
    """Fan out history, then calculate cross-sectional metrics exactly once."""
    with SessionLocal() as session:
        symbols = session.scalars(select(Instrument.symbol).where(Instrument.active.is_(True))).all()
    workflow = chord([backfill_symbol.s(symbol, months) for symbol in symbols])(finalize_universe_technicals.s())
    return {"queued": len(symbols), "months": months, "workflow_id": workflow.id}


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def calculate_symbol_technicals(symbol: str) -> dict:
    with SessionLocal() as session:
        return calculate_latest_technicals(session, symbol)


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def finalize_universe_technicals(_backfill_results: list[dict] | None = None) -> dict:
    """Run after the history fan-out completes to add relative strength and beta."""
    with SessionLocal() as session:
        metrics = calculate_universe_technicals(session)
        sectors = calculate_sector_metrics(session)
    return {"universe_metrics": metrics, "sectors": sectors}
