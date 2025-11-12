"""Health and monitoring API endpoints."""

from fastapi import APIRouter, Depends
from datetime import datetime
import aiosqlite

from app.db.sqlite import get_db
from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.authorization import get_authorization_service, AuthorizationService
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
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/stats")
async def get_statistics(db=Depends(get_db)):
    """Get detailed processing statistics.

    Provides insights into:
    - Job status breakdown
    - 24-hour performance metrics
    - Storage statistics
    - Celery worker status

    Args:
        db: Database instance

    Returns:
        dict: Comprehensive statistics
    """
    async with aiosqlite.connect(db.db_path) as conn:
        # Status breakdown
        async with conn.execute("""
            SELECT status, COUNT(*) as count
            FROM processing_jobs
            GROUP BY status
        """) as cursor:
            status_counts = {row[0]: row[1] for row in await cursor.fetchall()}

        # Performance metrics (last 24 hours)
        async with conn.execute("""
            SELECT
                COUNT(*) as total,
                AVG(CAST((julianday(completed_at) - julianday(created_at)) * 86400 AS REAL)) as avg_seconds
            FROM processing_jobs
            WHERE status = 'completed'
            AND created_at > datetime('now', '-24 hours')
        """) as cursor:
            row = await cursor.fetchone()
            performance = {
                "completed_24h": row[0] or 0,
                "avg_processing_time_seconds": round(row[1], 2) if row[1] else None
            }

        # Storage statistics
        async with conn.execute("""
            SELECT
                COUNT(DISTINCT image_id) as total_images,
                COUNT(*) as total_jobs
            FROM processing_jobs
        """) as cursor:
            row = await cursor.fetchone()
            storage = {
                "total_images": row[0],
                "total_jobs": row[1]
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
    except (TimeoutError, OSError, ConnectionError) as e:
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
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/failed")
async def get_failed_jobs(limit: int = 50, db=Depends(get_db)):
    """Get recent failed jobs for debugging.

    Args:
        limit: Maximum number of failed jobs to return (default: 50)
        db: Database instance

    Returns:
        dict: List of failed jobs with error details
    """
    async with aiosqlite.connect(db.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("""
            SELECT job_id, image_id, last_error, attempt_count, created_at, completed_at
            FROM processing_jobs
            WHERE status = 'failed'
            ORDER BY completed_at DESC
            LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()

    return {
        "failed_jobs": [
            {
                "job_id": row["job_id"],
                "image_id": row["image_id"],
                "error": row["last_error"],
                "attempts": row["attempt_count"],
                "created_at": row["created_at"],
                "failed_at": row["completed_at"]
            }
            for row in rows
        ],
        "total": len(rows)
    }


@router.get("/auth")
async def authorization_health_check(
    auth_service: AuthorizationService = Depends(get_authorization_service)
):
    """Authorization system health check.

    Provides insights into:
    - Auth-API connectivity and circuit breaker state
    - Redis cache connection and configuration
    - Authorization service configuration

    Returns:
        dict: Authorization system health metrics
    """
    # Get circuit breaker status
    circuit_breaker_status = await auth_service.get_circuit_breaker_status()

    # Check Redis connection
    redis_healthy = False
    redis_error = None
    try:
        await auth_service.redis.ping()
        redis_healthy = True
    except Exception as e:
        redis_error = str(e)
        logger.warning("auth_health_redis_check_failed", error=redis_error)

    # Determine overall health
    is_healthy = (
        redis_healthy and
        circuit_breaker_status["state"] != "open"
    )

    # Build response
    return {
        "status": "healthy" if is_healthy else "degraded",
        "auth_api": {
            "url": settings.AUTH_API_URL,
            "timeout_seconds": settings.AUTH_API_TIMEOUT,
            "circuit_breaker": {
                "state": circuit_breaker_status["state"],
                "failures": circuit_breaker_status.get("failures", 0),
                "threshold": settings.CIRCUIT_BREAKER_THRESHOLD,
                "timeout_seconds": settings.CIRCUIT_BREAKER_TIMEOUT,
                "opened_at": circuit_breaker_status.get("opened_at")
            }
        },
        "cache": {
            "enabled": settings.AUTH_CACHE_ENABLED,
            "redis_connection": "healthy" if redis_healthy else "down",
            "redis_error": redis_error,
            "ttl_config": {
                "read_seconds": settings.AUTH_CACHE_TTL_READ,
                "write_seconds": settings.AUTH_CACHE_TTL_WRITE,
                "admin_seconds": settings.AUTH_CACHE_TTL_ADMIN,
                "denied_seconds": settings.AUTH_CACHE_TTL_DENIED
            }
        },
        "config": {
            "fail_open": settings.AUTH_FAIL_OPEN
        },
        "timestamp": datetime.utcnow().isoformat()
    }
