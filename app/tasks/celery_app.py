"""Celery application configuration."""

from celery import Celery
from app.core.config import settings


# Initialize Celery app
celery_app = Celery(
    "image_processor",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL.replace("/0", "/1")  # Use Redis DB 1 for results
)

# Configure Celery from Settings (consistent with FastAPI config approach)
celery_app.conf.update(
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    accept_content=settings.CELERY_ACCEPT_CONTENT,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=settings.CELERY_ENABLE_UTC,
    task_track_started=settings.CELERY_TASK_TRACK_STARTED,
    task_acks_late=settings.CELERY_TASK_ACKS_LATE,
    worker_prefetch_multiplier=settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
    worker_max_tasks_per_child=settings.CELERY_WORKER_MAX_TASKS_PER_CHILD,
    # Redis connection options for redis-py 5.0+ compatibility
    # Disable health_check to avoid authentication errors with redis-py 5.0
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        'health_check_interval': 0,
    },
    redis_backend_health_check_interval=0,
)

# Import tasks to register them with Celery
from app.tasks.processing import process_image_task  # noqa: F401, E402


__all__ = ["celery_app", "process_image_task"]
