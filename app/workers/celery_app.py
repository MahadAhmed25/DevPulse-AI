from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "devpulse",
    broker=settings.redis_url_str,
    backend=settings.redis_url_str,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.run_pr_review": {"queue": "reviews"},
        "app.workers.tasks.index_repository": {"queue": "indexing"},
    },
    task_soft_time_limit=300,  # 5 minutes — task gets SoftTimeLimitExceeded
    task_time_limit=360,  # 6 minutes — worker kills the task
    result_expires=3600,
)
