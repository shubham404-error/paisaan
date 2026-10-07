"""Scheduled jobs. Wire Celery Beat/cloud scheduler to these task names."""
from backend.worker.celery_app import celery_app
from backend.services.market import overview


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def refresh_nifty_200_overview() -> dict:
    return overview()
