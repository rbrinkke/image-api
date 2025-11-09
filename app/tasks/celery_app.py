"""Celery application configuration."""

from celery import Celery
from app.core.config import settings


# Initialize Celery app
celery_app = Celery(
    "image_processor",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL.replace("/0", "/1")  # Use Redis DB 1 for results
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # Acknowledge after completion, not on start
    worker_prefetch_multiplier=1,  # Fetch one task at a time
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks (memory cleanup)
)

# Import tasks to register them with Celery
from app.tasks.processing import process_image_task  # noqa: F401, E402


__all__ = ["celery_app", "process_image_task"]
