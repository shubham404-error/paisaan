from celery import Celery

from backend.core.config import get_settings

settings = get_settings()
celery_app = Celery("paisaan", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.timezone = "Asia/Kolkata"
celery_app.conf.beat_schedule = {
    "nifty-200-eod-ingestion": {
        "task": "backend.worker.tasks.ingest_nifty_200_market_close",
        "schedule": 60 * 60 * 24,
    }
}
