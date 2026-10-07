from celery import Celery

from backend.core.config import get_settings

settings = get_settings()
celery_app = Celery("paisaan", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.timezone = "Asia/Kolkata"
