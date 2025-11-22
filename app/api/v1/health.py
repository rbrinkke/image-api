"""Health and monitoring API endpoints."""

from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import ProcessingJob
from app.core.config import settings
from app.core.logging_config import get_logger
from app.tasks.celery_app import celery_app


logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("/")
async def health_check():
    """Basic health check endpoint.

    Returns service status and version information.
    Use for load balancer health checks.

    Returns:
        dict: Health status with service info and timestamp
    """
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/stats")
async def get_statistics(session: AsyncSession = Depends(get_session)):
    """Get detailed processing statistics.

    Provides insights into:
    - Job status breakdown
    - 24-hour performance metrics
    - Storage statistics
    - Celery worker status

    Args:
        session: Database session

    Returns:
        dict: Comprehensive statistics
    """
    # Status breakdown
    stmt = select(ProcessingJob.status, func.count(ProcessingJob.job_id)).group_by(ProcessingJob.status)
    result = await session.execute(stmt)
    status_counts = {row[0]: row[1] for row in result.all()}

    # Performance metrics (last 24 hours)
    # SQLAlchemy doesn't have a generic 'julianday' function for all dialects.
    # We should use python calculation or dialect specific sql.
    # Since we use asyncpg (Postgres) or aiosqlite (SQLite), we need to be careful.
    # However, we can fetch the records and calculate in python if dataset is small,
    # or write compatible SQL.

    # For SQLite: julianday(completed_at) - julianday(created_at)
    # For Postgres: extract(epoch from (completed_at - created_at))

    # Let's try to be generic by fetching completed jobs in last 24h
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    stmt = select(ProcessingJob).where(
        ProcessingJob.status == 'completed',
        ProcessingJob.created_at > cutoff
    )
    result = await session.execute(stmt)
    jobs = result.scalars().all()

    total_completed_24h = len(jobs)
    total_duration = 0.0

    for job in jobs:
        if job.completed_at and job.created_at:
            # ensure timezones match or are aware
            start = job.created_at
            end = job.completed_at
            if start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)

            total_duration += (end - start).total_seconds()

    avg_seconds = round(total_duration / total_completed_24h, 2) if total_completed_24h > 0 else None

    performance = {
        "completed_24h": total_completed_24h,
        "avg_processing_time_seconds": avg_seconds
    }

    # Storage statistics
    # Count unique images
    stmt_images = select(func.count(func.distinct(ProcessingJob.image_id)))
    total_images = (await session.execute(stmt_images)).scalar() or 0

    stmt_jobs = select(func.count(ProcessingJob.job_id))
    total_jobs = (await session.execute(stmt_jobs)).scalar() or 0

    storage = {
        "total_images": total_images,
        "total_jobs": total_jobs
    }

    # Celery queue health
    try:
        # Use timeout to prevent blocking
        inspect = celery_app.control.inspect(timeout=2.0)
        active_tasks = inspect.active()

        celery_stats = {
            "active_workers": len(active_tasks) if active_tasks else 0,
            "active_tasks": sum(len(tasks) for tasks in active_tasks.values()) if active_tasks else 0
        }
    except (TimeoutError, OSError, ConnectionError, Exception) as e:
        # Specific handling for Celery connection failures
        logger.warning(
            "celery_inspection_failed",
            error_type=type(e).__name__,
            error=str(e),
        )

        celery_stats = {
            "active_workers": 0,
            "active_tasks": 0,
            "error": f"Could not connect to Celery: {type(e).__name__}"
        }

    return {
        "status_breakdown": status_counts,
        "performance_24h": performance,
        "storage": storage,
        "celery": celery_stats,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/failed")
async def get_failed_jobs(limit: int = 50, session: AsyncSession = Depends(get_session)):
    """Get recent failed jobs for debugging.

    Args:
        limit: Maximum number of failed jobs to return (default: 50)
        session: Database session

    Returns:
        dict: List of failed jobs with error details
    """
    stmt = select(ProcessingJob).where(
        ProcessingJob.status == 'failed'
    ).order_by(
        ProcessingJob.completed_at.desc()
    ).limit(limit)

    result = await session.execute(stmt)
    jobs = result.scalars().all()

    return {
        "failed_jobs": [
            {
                "job_id": job.job_id,
                "image_id": job.image_id,
                "error": job.last_error,
                "attempts": job.attempt_count,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "failed_at": job.completed_at.isoformat() if job.completed_at else None
            }
            for job in jobs
        ],
        "total": len(jobs)
    }


@router.get("/auth")
async def authorization_health_check():
    """Distributed Authorization System health check.

    Checks JWT validation, auth-api connectivity, circuit breaker status,
    and authorization cache health.

    Returns:
        dict: Authorization system status and configuration
    """
    import httpx
    from app.core.authorization import get_authorization_service

    # Get authorization service instance
    auth_service = await get_authorization_service()

    # Check circuit breaker status
    cb_state = "unknown"
    cb_failure_count = 0
    try:
        cb_state = await auth_service.circuit_breaker.get_state()
        cb_failure_count = await auth_service.circuit_breaker.get_failure_count()
    except Exception as e:
        logger.warning("circuit_breaker_health_check_failed", error=str(e))

    # Check auth-api connectivity
    auth_api_healthy = False
    auth_api_error = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.AUTH_API_URL}/health")
            auth_api_healthy = response.status_code == 200
    except Exception as e:
        auth_api_error = str(e)
        logger.warning("auth_api_health_check_failed", error=auth_api_error)

    # Overall health status
    overall_healthy = auth_api_healthy and cb_state == "closed"

    # Build response
    return {
        "status": "healthy" if overall_healthy else "degraded",
        "jwt_validation": {
            "mode": "HS256 Shared Secret",
            "issuer": settings.AUTH_API_ISSUER_URL,
            "audience": settings.AUTH_API_AUDIENCE,
            "algorithm": settings.JWT_ALGORITHM,
        },
        "authorization": {
            "enabled": True,
            "cache_enabled": settings.AUTH_CACHE_ENABLED,
            "cache_ttl_allowed_seconds": settings.AUTH_CACHE_TTL_ALLOWED,
            "cache_ttl_denied_seconds": settings.AUTH_CACHE_TTL_DENIED,
            "fail_mode": "closed" if not settings.AUTH_FAIL_OPEN else "open",
        },
        "circuit_breaker": {
            "enabled": settings.CIRCUIT_BREAKER_ENABLED,
            "state": cb_state,
            "failure_count": cb_failure_count,
            "threshold": settings.CIRCUIT_BREAKER_THRESHOLD,
            "timeout_seconds": settings.CIRCUIT_BREAKER_TIMEOUT,
        },
        "auth_api": {
            "url": settings.AUTH_API_URL,
            "status": "healthy" if auth_api_healthy else "down",
            "error": auth_api_error,
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
