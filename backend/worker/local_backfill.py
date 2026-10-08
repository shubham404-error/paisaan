"""Resumable local runner for the initial Nifty 200 history backfill.

Use this only for development when Redis/Celery is unavailable. Production uses
the queued `backfill_symbol` task instead.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

from sqlalchemy import select

from backend.db.database import SessionLocal
from backend.db.models import IngestionRun, Instrument
from backend.services.ingestion import backfill_history, calculate_latest_technicals, calculate_sector_metrics


def run(months: int, pause_seconds: float) -> None:
    with SessionLocal() as session:
        symbols = session.scalars(select(Instrument.symbol).where(Instrument.active.is_(True)).order_by(Instrument.symbol)).all()
        if not symbols:
            raise RuntimeError("No instruments found. Run Nifty 200 EOD ingestion before backfill.")
        ingestion_run = IngestionRun(job_name="nifty_200_history_backfill", status="running")
        session.add(ingestion_run)
        session.commit()
        run_id = ingestion_run.id

    completed, failed = 0, 0
    for position, symbol in enumerate(symbols, start=1):
        try:
            with SessionLocal() as session:
                count = backfill_history(session, symbol, months)
                metrics = calculate_latest_technicals(session, symbol)
            completed += 1
            print(f"[{position}/{len(symbols)}] {symbol}: {count} bars, RSI={metrics.get('rsi14')}", flush=True)
        except Exception as error:
            failed += 1
            print(f"[{position}/{len(symbols)}] {symbol}: FAILED {error}", flush=True)
        with SessionLocal() as session:
            ingestion_run = session.get(IngestionRun, run_id)
            ingestion_run.row_count = completed
            session.commit()
        if position < len(symbols):
            time.sleep(pause_seconds)

    with SessionLocal() as session:
        calculate_sector_metrics(session)
        ingestion_run = session.get(IngestionRun, run_id)
        ingestion_run.status = "completed" if not failed else "completed_with_errors"
        ingestion_run.completed_at = datetime.utcnow()
        ingestion_run.error = None if not failed else f"{failed} symbols failed; see runner log."
        session.commit()
    print(f"Finished: {completed} completed, {failed} failed", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=36)
    parser.add_argument("--pause-seconds", type=float, default=2.0)
    arguments = parser.parse_args()
    run(arguments.months, arguments.pause_seconds)
