"""Prometheus metrics endpoint and metric definitions."""

from fastapi import APIRouter, Response
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
)

from app.core.config import settings


# Create router
router = APIRouter(tags=["metrics"])


# Service info metric
service_info = Info(
    'service',
    'Service information',
    registry=REGISTRY
)
service_info.info({
    'name': settings.SERVICE_NAME,
    'version': settings.VERSION,
    'environment': settings.ENVIRONMENT,
})


# HTTP Request Metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['service', 'method', 'endpoint', 'status'],
    registry=REGISTRY
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['service', 'method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
    registry=REGISTRY
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'HTTP requests currently in progress',
    ['service', 'method'],
    registry=REGISTRY
)


# Image Processing Metrics
image_uploads_total = Counter(
    'image_uploads_total',
    'Total image uploads',
    ['service', 'status'],  # status: accepted, rejected
    registry=REGISTRY
)

image_processing_jobs_total = Counter(
    'image_processing_jobs_total',
    'Total image processing jobs',
    ['service', 'status'],  # status: completed, failed
    registry=REGISTRY
)

image_processing_duration_seconds = Histogram(
    'image_processing_duration_seconds',
    'Image processing duration in seconds',
    ['service', 'size'],  # size: thumbnail, medium, large, original
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0),
    registry=REGISTRY
)

image_processing_jobs_active = Gauge(
    'image_processing_jobs_active',
    'Currently active image processing jobs',
    ['service'],
    registry=REGISTRY
)

image_storage_bytes = Gauge(
    'image_storage_bytes',
    'Total storage used by images in bytes',
    ['service', 'size'],
    registry=REGISTRY
)


# Rate Limiting Metrics
rate_limit_rejections_total = Counter(
    'rate_limit_rejections_total',
    'Total requests rejected due to rate limiting',
    ['service', 'user_id'],
    registry=REGISTRY
)

rate_limit_current_usage = Gauge(
    'rate_limit_current_usage',
    'Current rate limit usage for users',
    ['service', 'user_id'],
    registry=REGISTRY
)


# Database Metrics
database_queries_total = Counter(
    'database_queries_total',
    'Total database queries',
    ['service', 'operation', 'table'],
    registry=REGISTRY
)

database_query_duration_seconds = Histogram(
    'database_query_duration_seconds',
    'Database query duration in seconds',
    ['service', 'operation', 'table'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=REGISTRY
)


# Storage Backend Metrics
storage_operations_total = Counter(
    'storage_operations_total',
    'Total storage operations',
    ['service', 'backend', 'operation', 'status'],  # operation: put, get, delete
    registry=REGISTRY
)

storage_operation_duration_seconds = Histogram(
    'storage_operation_duration_seconds',
    'Storage operation duration in seconds',
    ['service', 'backend', 'operation'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY
)


# Celery Worker Metrics
celery_tasks_total = Counter(
    'celery_tasks_total',
    'Total Celery tasks',
    ['service', 'task_name', 'status'],  # status: started, success, failure, retry
    registry=REGISTRY
)

celery_task_duration_seconds = Histogram(
    'celery_task_duration_seconds',
    'Celery task duration in seconds',
    ['service', 'task_name'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
    registry=REGISTRY
)

celery_queue_length = Gauge(
    'celery_queue_length',
    'Number of tasks in Celery queue',
    ['service', 'queue'],
    registry=REGISTRY
)


# Error Tracking Metrics
errors_total = Counter(
    'errors_total',
    'Total errors',
    ['service', 'error_type', 'endpoint'],
    registry=REGISTRY
)


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format for scraping.
    This endpoint should be called by Prometheus at regular intervals.

    Returns:
        Response: Prometheus metrics in text format
    """
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST
    )
