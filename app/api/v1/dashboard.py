"""Technical dashboard API for system monitoring and troubleshooting."""

import aiosqlite
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
import psutil
import os

from app.db.sqlite import get_db
from app.core.config import settings
from app.core.logging_config import get_logger
from app.tasks.celery_app import celery_app


logger = get_logger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# Track application start time for uptime calculation
_start_time = datetime.utcnow()


async def get_redis_info() -> Dict[str, Any]:
    """Get Redis server information and statistics.

    Returns:
        dict: Redis status and metrics
    """
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.REDIS_URL, decode_responses=True)

        # Get Redis INFO
        info = await client.info()

        # Get queue lengths
        celery_queue_len = await client.llen("celery")

        await client.close()

        return {
            "status": "healthy",
            "connected": True,
            "info": {
                "used_memory_human": info.get("used_memory_human", "N/A"),
                "used_memory_peak_human": info.get("used_memory_peak_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "role": info.get("role", "unknown"),
                "redis_version": info.get("redis_version", "unknown")
            },
            "queue_lengths": {
                "celery": celery_queue_len
            }
        }
    except Exception as e:
        logger.error(f"Failed to get Redis info: {e}")
        return {
            "status": "down",
            "connected": False,
            "error": str(e)
        }


async def get_celery_info() -> Dict[str, Any]:
    """Get Celery worker and task information.

    Returns:
        dict: Celery status and metrics
    """
    try:
        inspect = celery_app.control.inspect(timeout=2.0)

        # Get active tasks
        active_tasks = inspect.active() or {}

        # Get reserved tasks
        reserved_tasks = inspect.reserved() or {}

        # Get scheduled tasks
        scheduled_tasks = inspect.scheduled() or {}

        # Get registered tasks
        registered = inspect.registered() or {}

        # Get worker stats
        stats = inspect.stats() or {}

        # Calculate totals
        total_active = sum(len(tasks) for tasks in active_tasks.values())
        total_reserved = sum(len(tasks) for tasks in reserved_tasks.values())
        total_scheduled = sum(len(tasks) for tasks in scheduled_tasks.values())

        # Extract unique registered task names
        all_registered_tasks = set()
        for worker_tasks in registered.values():
            all_registered_tasks.update(worker_tasks)

        return {
            "status": "healthy" if len(active_tasks) > 0 else "degraded",
            "workers": {
                "active": len(active_tasks),
                "registered": list(active_tasks.keys()) if active_tasks else [],
                "stats": stats
            },
            "tasks": {
                "active": total_active,
                "reserved": total_reserved,
                "scheduled": total_scheduled,
                "active_details": active_tasks,
                "reserved_details": reserved_tasks
            },
            "registered_tasks": sorted(list(all_registered_tasks))
        }
    except (TimeoutError, OSError, ConnectionError) as e:
        logger.warning(f"Celery inspection failed: {type(e).__name__}: {e}")
        return {
            "status": "down",
            "error": f"Could not connect to Celery: {type(e).__name__}",
            "workers": {"active": 0, "registered": []},
            "tasks": {"active": 0, "reserved": 0, "scheduled": 0}
        }


async def get_database_info(db) -> Dict[str, Any]:
    """Get database health and statistics.

    Args:
        db: Database instance

    Returns:
        dict: Database status and metrics
    """
    try:
        async with aiosqlite.connect(db.db_path) as conn:
            # Get table counts
            tables = {}
            for table in ["processing_jobs", "image_upload_events", "upload_rate_limits"]:
                async with conn.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                    row = await cursor.fetchone()
                    tables[table] = row[0] if row else 0

            # Get recent activity
            async with conn.execute("""
                SELECT created_at FROM processing_jobs
                ORDER BY created_at DESC LIMIT 1
            """) as cursor:
                row = await cursor.fetchone()
                last_job_created = row[0] if row else None

            async with conn.execute("""
                SELECT created_at FROM image_upload_events
                ORDER BY created_at DESC LIMIT 1
            """) as cursor:
                row = await cursor.fetchone()
                last_event_logged = row[0] if row else None

            # Get database file size
            db_size_bytes = Path(db.db_path).stat().st_size
            db_size_mb = round(db_size_bytes / (1024 * 1024), 2)

            return {
                "status": "healthy",
                "path": db.db_path,
                "size_mb": db_size_mb,
                "connection_ok": True,
                "tables": tables,
                "recent_activity": {
                    "last_job_created": last_job_created,
                    "last_event_logged": last_event_logged
                }
            }
    except Exception as e:
        logger.error(f"Failed to get database info: {e}")
        return {
            "status": "down",
            "connection_ok": False,
            "error": str(e)
        }


async def get_processing_metrics(db) -> Dict[str, Any]:
    """Get processing job metrics and performance data.

    Args:
        db: Database instance

    Returns:
        dict: Processing metrics
    """
    try:
        async with aiosqlite.connect(db.db_path) as conn:
            # Jobs by status
            async with conn.execute("""
                SELECT status, COUNT(*) as count
                FROM processing_jobs
                GROUP BY status
            """) as cursor:
                jobs_by_status = {row[0]: row[1] for row in await cursor.fetchall()}

            # Last hour performance
            async with conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    AVG(CASE
                        WHEN status = 'completed' AND completed_at IS NOT NULL
                        THEN (julianday(completed_at) - julianday(created_at)) * 86400
                        ELSE NULL
                    END) as avg_seconds
                FROM processing_jobs
                WHERE created_at > datetime('now', '-1 hour')
            """) as cursor:
                row = await cursor.fetchone()
                last_hour = {
                    "total": row[0] or 0,
                    "completed": row[1] or 0,
                    "failed": row[2] or 0,
                    "avg_processing_time_seconds": round(row[3], 2) if row[3] else None
                }

            # Last 24h performance
            async with conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    AVG(CASE
                        WHEN status = 'completed' AND completed_at IS NOT NULL
                        THEN (julianday(completed_at) - julianday(created_at)) * 86400
                        ELSE NULL
                    END) as avg_seconds
                FROM processing_jobs
                WHERE created_at > datetime('now', '-24 hours')
            """) as cursor:
                row = await cursor.fetchone()
                last_24h = {
                    "total": row[0] or 0,
                    "completed": row[1] or 0,
                    "failed": row[2] or 0,
                    "avg_processing_time_seconds": round(row[3], 2) if row[3] else None
                }

            # Recent jobs (last 10)
            conn.row_factory = aiosqlite.Row
            async with conn.execute("""
                SELECT
                    job_id, image_id, status, created_at, completed_at,
                    (julianday(COALESCE(completed_at, datetime('now'))) - julianday(created_at)) * 86400 as processing_time
                FROM processing_jobs
                ORDER BY created_at DESC
                LIMIT 10
            """) as cursor:
                rows = await cursor.fetchall()
                recent_jobs = [
                    {
                        "job_id": row["job_id"],
                        "image_id": row["image_id"],
                        "status": row["status"],
                        "created_at": row["created_at"],
                        "completed_at": row["completed_at"],
                        "processing_time_seconds": round(row["processing_time"], 2) if row["processing_time"] else None
                    }
                    for row in rows
                ]

            return {
                "jobs_by_status": jobs_by_status,
                "performance": {
                    "last_hour": last_hour,
                    "last_24h": last_24h
                },
                "recent_jobs": recent_jobs
            }
    except Exception as e:
        logger.error(f"Failed to get processing metrics: {e}")
        return {
            "error": str(e)
        }


async def get_storage_info(db) -> Dict[str, Any]:
    """Get storage backend information.

    Args:
        db: Database instance

    Returns:
        dict: Storage status and metrics
    """
    try:
        info = {
            "backend": settings.STORAGE_BACKEND,
        }

        if settings.STORAGE_BACKEND == "local":
            storage_path = Path(settings.STORAGE_PATH)
            if storage_path.exists():
                # Get disk usage
                disk_usage = psutil.disk_usage(str(storage_path))
                info["path"] = settings.STORAGE_PATH
                info["disk_total_gb"] = round(disk_usage.total / (1024**3), 2)
                info["disk_used_gb"] = round(disk_usage.used / (1024**3), 2)
                info["disk_free_gb"] = round(disk_usage.free / (1024**3), 2)
                info["disk_percent_used"] = disk_usage.percent

                # Count files
                total_files = sum(1 for _ in storage_path.rglob("*") if _.is_file())
                info["total_files"] = total_files
            else:
                info["path"] = settings.STORAGE_PATH
                info["exists"] = False
        else:  # S3
            info["region"] = settings.AWS_REGION

        # Get total unique images from database
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute("""
                SELECT COUNT(DISTINCT image_id) FROM processing_jobs
                WHERE status = 'completed'
            """) as cursor:
                row = await cursor.fetchone()
                info["total_images"] = row[0] if row else 0

        return info
    except Exception as e:
        logger.error(f"Failed to get storage info: {e}")
        return {
            "backend": settings.STORAGE_BACKEND,
            "error": str(e)
        }


async def get_rate_limit_info(db) -> Dict[str, Any]:
    """Get rate limiting statistics.

    Args:
        db: Database instance

    Returns:
        dict: Rate limit metrics
    """
    try:
        async with aiosqlite.connect(db.db_path) as conn:
            conn.row_factory = aiosqlite.Row

            # Get users near limit (>80% of limit)
            threshold = int(settings.RATE_LIMIT_MAX_UPLOADS * 0.8)
            async with conn.execute("""
                SELECT user_id, upload_count, window_start
                FROM upload_rate_limits
                WHERE upload_count >= ?
                ORDER BY upload_count DESC
                LIMIT 10
            """, (threshold,)) as cursor:
                rows = await cursor.fetchall()
                users_near_limit = [
                    {
                        "user_id": row["user_id"],
                        "count": row["upload_count"],
                        "limit": settings.RATE_LIMIT_MAX_UPLOADS,
                        "window_start": row["window_start"],
                        "percent_used": round((row["upload_count"] / settings.RATE_LIMIT_MAX_UPLOADS) * 100, 1)
                    }
                    for row in rows
                ]

            # Get total active windows
            async with conn.execute("""
                SELECT COUNT(*) FROM upload_rate_limits
            """) as cursor:
                row = await cursor.fetchone()
                total_active_windows = row[0] if row else 0

            return {
                "users_near_limit": users_near_limit,
                "total_active_windows": total_active_windows,
                "max_uploads_per_hour": settings.RATE_LIMIT_MAX_UPLOADS
            }
    except Exception as e:
        logger.error(f"Failed to get rate limit info: {e}")
        return {"error": str(e)}


async def get_error_info(db) -> Dict[str, Any]:
    """Get error and failure statistics.

    Args:
        db: Database instance

    Returns:
        dict: Error metrics
    """
    try:
        async with aiosqlite.connect(db.db_path) as conn:
            conn.row_factory = aiosqlite.Row

            # Recent failures (last 10)
            async with conn.execute("""
                SELECT job_id, image_id, last_error, attempt_count, created_at, completed_at
                FROM processing_jobs
                WHERE status = 'failed'
                ORDER BY completed_at DESC
                LIMIT 10
            """) as cursor:
                rows = await cursor.fetchall()
                recent_failures = [
                    {
                        "job_id": row["job_id"],
                        "image_id": row["image_id"],
                        "error": row["last_error"],
                        "attempts": row["attempt_count"],
                        "created_at": row["created_at"],
                        "failed_at": row["completed_at"]
                    }
                    for row in rows
                ]

            # Error summary
            async with conn.execute("""
                SELECT
                    SUM(CASE WHEN created_at > datetime('now', '-1 hour') THEN 1 ELSE 0 END) as last_hour,
                    SUM(CASE WHEN created_at > datetime('now', '-24 hours') THEN 1 ELSE 0 END) as last_24h,
                    COUNT(*) as total
                FROM processing_jobs
                WHERE status = 'failed'
            """) as cursor:
                row = await cursor.fetchone()
                error_summary = {
                    "last_hour": row[0] if row else 0,
                    "last_24h": row[1] if row else 0,
                    "total": row[2] if row else 0
                }

            return {
                "recent_failures": recent_failures,
                "error_summary": error_summary
            }
    except Exception as e:
        logger.error(f"Failed to get error info: {e}")
        return {"error": str(e)}


async def get_system_info() -> Dict[str, Any]:
    """Get system resource information.

    Returns:
        dict: System metrics
    """
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()

        # Memory usage
        memory = psutil.virtual_memory()

        # Disk usage for root
        disk = psutil.disk_usage('/')

        # Process info
        process = psutil.Process(os.getpid())
        process_memory = process.memory_info()

        # Uptime
        uptime_seconds = (datetime.utcnow() - _start_time).total_seconds()

        return {
            "service_name": settings.SERVICE_NAME,
            "version": settings.VERSION,
            "uptime_seconds": round(uptime_seconds, 1),
            "uptime_human": str(timedelta(seconds=int(uptime_seconds))),
            "timestamp": datetime.utcnow().isoformat(),
            "resources": {
                "cpu": {
                    "percent": cpu_percent,
                    "count": cpu_count
                },
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "used_gb": round(memory.used / (1024**3), 2),
                    "percent": memory.percent
                },
                "disk_root": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "percent": disk.percent
                },
                "process": {
                    "memory_rss_mb": round(process_memory.rss / (1024**2), 2),
                    "memory_vms_mb": round(process_memory.vms / (1024**2), 2),
                    "threads": process.num_threads()
                }
            }
        }
    except Exception as e:
        logger.error(f"Failed to get system info: {e}")
        return {
            "service_name": settings.SERVICE_NAME,
            "version": settings.VERSION,
            "uptime_seconds": (datetime.utcnow() - _start_time).total_seconds(),
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


@router.get("/data")
async def get_dashboard_data(db=Depends(get_db)):
    """Get comprehensive dashboard data for monitoring and troubleshooting.

    Returns all technical metrics in a single response:
    - System resources and uptime
    - Database health and statistics
    - Redis status and metrics
    - Celery worker and task information
    - Processing job metrics
    - Storage backend information
    - Rate limiting status
    - Error tracking and recent failures
    - Configuration summary

    Args:
        db: Database instance

    Returns:
        dict: Complete dashboard data
    """
    # Gather all metrics concurrently would be ideal, but for simplicity we'll do sequential
    system = await get_system_info()
    database = await get_database_info(db)
    redis_info = await get_redis_info()
    celery_info = await get_celery_info()
    processing = await get_processing_metrics(db)
    storage = await get_storage_info(db)
    rate_limits = await get_rate_limit_info(db)
    errors = await get_error_info(db)

    return {
        "system": system,
        "database": database,
        "redis": redis_info,
        "celery": celery_info,
        "processing": processing,
        "storage": storage,
        "rate_limits": rate_limits,
        "errors": errors,
        "configuration": {
            "rate_limit_max_uploads": settings.RATE_LIMIT_MAX_UPLOADS,
            "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB,
            "webp_quality": settings.WEBP_QUALITY,
            "allowed_mime_types": settings.ALLOWED_MIME_TYPES,
            "image_sizes": settings.IMAGE_SIZES,
            "celery_worker_prefetch": settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
            "celery_max_tasks_per_child": settings.CELERY_WORKER_MAX_TASKS_PER_CHILD
        }
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard_ui():
    """Serve interactive HTML dashboard for system monitoring.

    Returns:
        HTMLResponse: Dashboard interface with auto-refresh
    """
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image Processor - Technical Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            background: #0a0a0a;
            color: #e0e0e0;
            padding: 20px;
            font-size: 13px;
            line-height: 1.4;
        }

        .header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 20px 30px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #00d4ff;
        }

        .header h1 {
            color: #00d4ff;
            font-size: 24px;
            margin-bottom: 8px;
        }

        .header .meta {
            color: #888;
            font-size: 12px;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .section {
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            transition: all 0.3s ease;
        }

        .section:hover {
            border-color: #3a3a3a;
            box-shadow: 0 4px 20px rgba(0, 212, 255, 0.1);
        }

        .section h2 {
            color: #00d4ff;
            font-size: 16px;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #2a2a2a;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        .metric-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #1a1a1a;
        }

        .metric-row:last-child {
            border-bottom: none;
        }

        .metric-label {
            color: #999;
            font-weight: 600;
        }

        .metric-value {
            color: #fff;
            font-weight: bold;
        }

        .status {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            text-transform: uppercase;
        }

        .status.healthy { background: #00ff41; color: #000; }
        .status.degraded { background: #ffaa00; color: #000; }
        .status.down { background: #ff0040; color: #fff; }
        .status.pending { background: #888; color: #fff; }
        .status.processing { background: #00aaff; color: #fff; }
        .status.completed { background: #00ff41; color: #000; }
        .status.failed { background: #ff0040; color: #fff; }

        .table {
            width: 100%;
            margin-top: 10px;
            border-collapse: collapse;
        }

        .table th {
            background: #0f0f0f;
            color: #00d4ff;
            padding: 8px;
            text-align: left;
            font-size: 11px;
            text-transform: uppercase;
            border-bottom: 2px solid #2a2a2a;
        }

        .table td {
            padding: 8px;
            border-bottom: 1px solid #1a1a1a;
            font-size: 12px;
        }

        .table tr:hover {
            background: #0f0f0f;
        }

        .error-text {
            color: #ff0040;
            font-family: monospace;
            font-size: 11px;
            background: #1a0505;
            padding: 4px 8px;
            border-radius: 4px;
            margin-top: 4px;
            word-break: break-all;
        }

        .warning {
            background: #332200;
            border-left: 4px solid #ffaa00;
            padding: 12px;
            margin: 10px 0;
            border-radius: 4px;
            color: #ffaa00;
        }

        .info {
            background: #002233;
            border-left: 4px solid #00aaff;
            padding: 12px;
            margin: 10px 0;
            border-radius: 4px;
            color: #00aaff;
        }

        .refresh-indicator {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #1a1a2e;
            padding: 10px 20px;
            border-radius: 20px;
            border: 1px solid #2a2a2a;
            color: #00d4ff;
            font-size: 12px;
            z-index: 1000;
        }

        .refresh-indicator.loading {
            animation: pulse 1s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .progress-bar {
            width: 100%;
            height: 8px;
            background: #0f0f0f;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 6px;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #00d4ff, #00ff41);
            transition: width 0.3s ease;
        }

        .badge {
            display: inline-block;
            padding: 2px 8px;
            background: #2a2a2a;
            border-radius: 4px;
            font-size: 11px;
            margin: 2px;
        }

        .full-width {
            grid-column: 1 / -1;
        }

        code {
            background: #0f0f0f;
            padding: 2px 6px;
            border-radius: 3px;
            color: #00ff41;
            font-size: 11px;
        }
    </style>
</head>
<body>
    <div class="refresh-indicator" id="refreshIndicator">
        Auto-refresh: <span id="countdown">5</span>s
    </div>

    <div class="header">
        <h1>⚡ IMAGE PROCESSOR - TECHNICAL DASHBOARD</h1>
        <div class="meta">
            <span id="systemInfo">Loading...</span> |
            Last update: <span id="lastUpdate">Never</span>
        </div>
    </div>

    <div id="dashboard">
        <div style="text-align: center; padding: 40px; color: #666;">
            <div style="font-size: 48px; margin-bottom: 20px;">⚙️</div>
            <div>Loading dashboard data...</div>
        </div>
    </div>

    <script>
        let countdownSeconds = 5;
        let countdownInterval;

        function updateCountdown() {
            document.getElementById('countdown').textContent = countdownSeconds;
            if (countdownSeconds <= 0) {
                countdownSeconds = 5;
                loadDashboard();
            } else {
                countdownSeconds--;
            }
        }

        function startCountdown() {
            if (countdownInterval) clearInterval(countdownInterval);
            countdownSeconds = 5;
            countdownInterval = setInterval(updateCountdown, 1000);
        }

        function formatUptime(seconds) {
            const days = Math.floor(seconds / 86400);
            const hours = Math.floor((seconds % 86400) / 3600);
            const mins = Math.floor((seconds % 3600) / 60);
            const secs = Math.floor(seconds % 60);

            if (days > 0) return `${days}d ${hours}h ${mins}m`;
            if (hours > 0) return `${hours}h ${mins}m ${secs}s`;
            if (mins > 0) return `${mins}m ${secs}s`;
            return `${secs}s`;
        }

        function formatBytes(bytes) {
            if (bytes >= 1024*1024*1024) return (bytes / (1024*1024*1024)).toFixed(2) + ' GB';
            if (bytes >= 1024*1024) return (bytes / (1024*1024)).toFixed(2) + ' MB';
            if (bytes >= 1024) return (bytes / 1024).toFixed(2) + ' KB';
            return bytes + ' B';
        }

        function getStatusClass(status) {
            if (!status) return 'degraded';
            return status.toLowerCase();
        }

        function renderMetricRow(label, value, valueClass = '') {
            return `
                <div class="metric-row">
                    <span class="metric-label">${label}</span>
                    <span class="metric-value ${valueClass}">${value}</span>
                </div>
            `;
        }

        function renderDashboard(data) {
            const sys = data.system;
            const db = data.database;
            const redis = data.redis;
            const celery = data.celery;
            const proc = data.processing;
            const storage = data.storage;
            const limits = data.rate_limits;
            const errors = data.errors;
            const config = data.configuration;

            // Update header
            document.getElementById('systemInfo').innerHTML =
                `${sys.service_name} v${sys.version} | Uptime: ${sys.uptime_human || formatUptime(sys.uptime_seconds)}`;
            document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();

            // Build dashboard HTML
            let html = '<div class="grid">';

            // System Resources
            html += `
                <div class="section">
                    <h2>🖥️ System Resources</h2>
                    ${renderMetricRow('CPU Usage', `${sys.resources?.cpu?.percent || 0}% (${sys.resources?.cpu?.count || 0} cores)`)}
                    ${renderMetricRow('Memory Usage', `${sys.resources?.memory?.used_gb || 0} GB / ${sys.resources?.memory?.total_gb || 0} GB (${sys.resources?.memory?.percent || 0}%)`)}
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${sys.resources?.memory?.percent || 0}%"></div>
                    </div>
                    ${renderMetricRow('Disk (Root)', `${sys.resources?.disk_root?.used_gb || 0} GB / ${sys.resources?.disk_root?.total_gb || 0} GB (${sys.resources?.disk_root?.percent || 0}%)`)}
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${sys.resources?.disk_root?.percent || 0}%"></div>
                    </div>
                    ${renderMetricRow('Process Memory', `RSS: ${sys.resources?.process?.memory_rss_mb || 0} MB | VMS: ${sys.resources?.process?.memory_vms_mb || 0} MB`)}
                    ${renderMetricRow('Threads', sys.resources?.process?.threads || 0)}
                </div>
            `;

            // Database Health
            html += `
                <div class="section">
                    <h2>💾 Database Health</h2>
                    ${renderMetricRow('Status', `<span class="status ${getStatusClass(db.status)}">${db.status || 'unknown'}</span>`)}
                    ${renderMetricRow('Path', `<code>${db.path || 'N/A'}</code>`)}
                    ${renderMetricRow('Size', `${db.size_mb || 0} MB`)}
                    ${renderMetricRow('Processing Jobs', (db.tables?.processing_jobs || 0).toLocaleString())}
                    ${renderMetricRow('Upload Events', (db.tables?.image_upload_events || 0).toLocaleString())}
                    ${renderMetricRow('Rate Limit Records', (db.tables?.upload_rate_limits || 0).toLocaleString())}
                    ${renderMetricRow('Last Job Created', db.recent_activity?.last_job_created || 'Never')}
                </div>
            `;

            // Redis Status
            html += `
                <div class="section">
                    <h2>🔴 Redis Status</h2>
                    ${renderMetricRow('Status', `<span class="status ${getStatusClass(redis.status)}">${redis.status}</span>`)}
                    ${renderMetricRow('Connected', redis.connected ? '✅ Yes' : '❌ No')}
                    ${redis.info ? `
                        ${renderMetricRow('Version', redis.info.redis_version)}
                        ${renderMetricRow('Memory Used', redis.info.used_memory_human)}
                        ${renderMetricRow('Memory Peak', redis.info.used_memory_peak_human)}
                        ${renderMetricRow('Connected Clients', redis.info.connected_clients)}
                        ${renderMetricRow('Ops/sec', redis.info.instantaneous_ops_per_sec.toLocaleString())}
                        ${renderMetricRow('Total Commands', redis.info.total_commands_processed.toLocaleString())}
                        ${renderMetricRow('Uptime', formatUptime(redis.info.uptime_in_seconds))}
                        ${renderMetricRow('Celery Queue Length', redis.queue_lengths?.celery || 0)}
                    ` : ''}
                    ${redis.error ? `<div class="error-text">${redis.error}</div>` : ''}
                </div>
            `;

            // Celery Workers
            html += `
                <div class="section">
                    <h2>⚙️ Celery Workers</h2>
                    ${renderMetricRow('Status', `<span class="status ${getStatusClass(celery.status)}">${celery.status}</span>`)}
                    ${renderMetricRow('Active Workers', celery.workers?.active || 0)}
                    ${renderMetricRow('Active Tasks', celery.tasks?.active || 0)}
                    ${renderMetricRow('Reserved Tasks', celery.tasks?.reserved || 0)}
                    ${renderMetricRow('Scheduled Tasks', celery.tasks?.scheduled || 0)}
                    ${celery.workers?.registered && celery.workers.registered.length > 0 ? `
                        <div style="margin-top: 10px;">
                            <div class="metric-label" style="margin-bottom: 5px;">Workers:</div>
                            ${celery.workers.registered.map(w => `<div class="badge">${w}</div>`).join('')}
                        </div>
                    ` : ''}
                    ${celery.registered_tasks && celery.registered_tasks.length > 0 ? `
                        <div style="margin-top: 10px;">
                            <div class="metric-label" style="margin-bottom: 5px;">Registered Tasks:</div>
                            ${celery.registered_tasks.map(t => `<div class="badge">${t.split('.').pop()}</div>`).join('')}
                        </div>
                    ` : ''}
                    ${celery.error ? `<div class="error-text">${celery.error}</div>` : ''}
                </div>
            `;

            // Processing Metrics
            const totalJobs = Object.values(proc.jobs_by_status || {}).reduce((a, b) => a + b, 0);
            html += `
                <div class="section">
                    <h2>📊 Processing Metrics</h2>
                    ${renderMetricRow('Total Jobs', totalJobs.toLocaleString())}
                    ${Object.entries(proc.jobs_by_status || {}).map(([status, count]) =>
                        renderMetricRow(status.charAt(0).toUpperCase() + status.slice(1),
                        `<span class="status ${status}">${count.toLocaleString()}</span>`)
                    ).join('')}
                    <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #2a2a2a;">
                        <div class="metric-label" style="margin-bottom: 10px;">Last Hour</div>
                        ${renderMetricRow('Total', proc.performance?.last_hour?.total || 0)}
                        ${renderMetricRow('Completed', proc.performance?.last_hour?.completed || 0)}
                        ${renderMetricRow('Failed', proc.performance?.last_hour?.failed || 0)}
                        ${renderMetricRow('Avg Time', proc.performance?.last_hour?.avg_processing_time_seconds ?
                            `${proc.performance.last_hour.avg_processing_time_seconds.toFixed(2)}s` : 'N/A')}
                    </div>
                    <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #2a2a2a;">
                        <div class="metric-label" style="margin-bottom: 10px;">Last 24 Hours</div>
                        ${renderMetricRow('Total', proc.performance?.last_24h?.total || 0)}
                        ${renderMetricRow('Completed', proc.performance?.last_24h?.completed || 0)}
                        ${renderMetricRow('Failed', proc.performance?.last_24h?.failed || 0)}
                        ${renderMetricRow('Avg Time', proc.performance?.last_24h?.avg_processing_time_seconds ?
                            `${proc.performance.last_24h.avg_processing_time_seconds.toFixed(2)}s` : 'N/A')}
                    </div>
                </div>
            `;

            // Storage Info
            html += `
                <div class="section">
                    <h2>💿 Storage Backend</h2>
                    ${renderMetricRow('Backend', `<code>${storage.backend}</code>`)}
                    ${storage.backend === 'local' ? `
                        ${renderMetricRow('Path', `<code>${storage.path}</code>`)}
                        ${storage.disk_total_gb ? `
                            ${renderMetricRow('Total Space', `${storage.disk_total_gb} GB`)}
                            ${renderMetricRow('Used Space', `${storage.disk_used_gb} GB`)}
                            ${renderMetricRow('Free Space', `${storage.disk_free_gb} GB`)}
                            ${renderMetricRow('Usage', `${storage.disk_percent_used}%`)}
                            <div class="progress-bar">
                                <div class="progress-fill" style="width: ${storage.disk_percent_used}%"></div>
                            </div>
                            ${renderMetricRow('Total Files', (storage.total_files || 0).toLocaleString())}
                        ` : ''}
                    ` : `
                        ${renderMetricRow('Region', storage.region)}
                    `}
                    ${renderMetricRow('Total Images', (storage.total_images || 0).toLocaleString())}
                    ${storage.error ? `<div class="error-text">${storage.error}</div>` : ''}
                </div>
            `;

            // Rate Limiting
            html += `
                <div class="section">
                    <h2>⏱️ Rate Limiting</h2>
                    ${renderMetricRow('Max Uploads/Hour', limits.max_uploads_per_hour)}
                    ${renderMetricRow('Active Windows', limits.total_active_windows || 0)}
                    ${limits.users_near_limit && limits.users_near_limit.length > 0 ? `
                        <div class="warning">
                            ⚠️ ${limits.users_near_limit.length} user(s) near limit (≥80%)
                        </div>
                        <table class="table" style="margin-top: 10px;">
                            <thead>
                                <tr>
                                    <th>User ID</th>
                                    <th>Usage</th>
                                    <th>Window</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${limits.users_near_limit.slice(0, 5).map(u => `
                                    <tr>
                                        <td><code>${u.user_id}</code></td>
                                        <td>${u.count}/${u.limit} (${u.percent_used}%)</td>
                                        <td>${new Date(u.window_start).toLocaleString()}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    ` : `
                        <div class="info">✅ No users near rate limit</div>
                    `}
                </div>
            `;

            // Configuration
            html += `
                <div class="section">
                    <h2>⚙️ Configuration</h2>
                    ${renderMetricRow('WebP Quality', `${config.webp_quality}%`)}
                    ${renderMetricRow('Max Upload Size', `${config.max_upload_size_mb} MB`)}
                    ${renderMetricRow('Worker Prefetch', config.celery_worker_prefetch)}
                    ${renderMetricRow('Max Tasks/Child', config.celery_max_tasks_per_child)}
                    <div style="margin-top: 10px;">
                        <div class="metric-label" style="margin-bottom: 5px;">Allowed MIME Types:</div>
                        ${config.allowed_mime_types.map(t => `<div class="badge">${t}</div>`).join('')}
                    </div>
                    <div style="margin-top: 10px;">
                        <div class="metric-label" style="margin-bottom: 5px;">Image Sizes:</div>
                        ${Object.entries(config.image_sizes).map(([k, v]) =>
                            `<div class="badge">${k}: ${v}px</div>`
                        ).join('')}
                    </div>
                </div>
            `;

            html += '</div>'; // End grid

            // Recent Jobs (Full Width)
            if (proc.recent_jobs && proc.recent_jobs.length > 0) {
                html += `
                    <div class="section full-width" style="margin-top: 20px;">
                        <h2>📋 Recent Jobs (Last 10)</h2>
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Job ID</th>
                                    <th>Image ID</th>
                                    <th>Status</th>
                                    <th>Created At</th>
                                    <th>Completed At</th>
                                    <th>Processing Time</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${proc.recent_jobs.map(job => `
                                    <tr>
                                        <td><code>${job.job_id.substring(0, 8)}...</code></td>
                                        <td><code>${job.image_id.substring(0, 8)}...</code></td>
                                        <td><span class="status ${job.status}">${job.status}</span></td>
                                        <td>${new Date(job.created_at).toLocaleString()}</td>
                                        <td>${job.completed_at ? new Date(job.completed_at).toLocaleString() : '-'}</td>
                                        <td>${job.processing_time_seconds ? job.processing_time_seconds.toFixed(2) + 's' : '-'}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
            }

            // Recent Failures (Full Width)
            if (errors.recent_failures && errors.recent_failures.length > 0) {
                html += `
                    <div class="section full-width" style="margin-top: 20px;">
                        <h2>❌ Recent Failures</h2>
                        <div style="margin-bottom: 15px;">
                            ${renderMetricRow('Failed (Last Hour)', errors.error_summary?.last_hour || 0)}
                            ${renderMetricRow('Failed (Last 24h)', errors.error_summary?.last_24h || 0)}
                            ${renderMetricRow('Total Failed', errors.error_summary?.total || 0)}
                        </div>
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Job ID</th>
                                    <th>Image ID</th>
                                    <th>Error</th>
                                    <th>Attempts</th>
                                    <th>Failed At</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${errors.recent_failures.slice(0, 10).map(job => `
                                    <tr>
                                        <td><code>${job.job_id.substring(0, 8)}...</code></td>
                                        <td><code>${job.image_id.substring(0, 8)}...</code></td>
                                        <td><div class="error-text" style="max-width: 400px; overflow: hidden; text-overflow: ellipsis;">${job.error || 'Unknown'}</div></td>
                                        <td>${job.attempts}</td>
                                        <td>${job.failed_at ? new Date(job.failed_at).toLocaleString() : '-'}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
            } else {
                html += `
                    <div class="section full-width" style="margin-top: 20px;">
                        <h2>❌ Recent Failures</h2>
                        <div class="info">✅ No recent failures - system operating normally</div>
                    </div>
                `;
            }

            document.getElementById('dashboard').innerHTML = html;
        }

        async function loadDashboard() {
            try {
                document.getElementById('refreshIndicator').classList.add('loading');
                const response = await fetch('/dashboard/data');
                const data = await response.json();
                renderDashboard(data);
            } catch (error) {
                console.error('Failed to load dashboard:', error);
                document.getElementById('dashboard').innerHTML = `
                    <div class="section" style="text-align: center; padding: 40px;">
                        <h2 style="color: #ff0040;">⚠️ Failed to Load Dashboard</h2>
                        <div class="error-text" style="margin-top: 20px;">${error.message}</div>
                        <div style="margin-top: 20px; color: #666;">Retrying in 5 seconds...</div>
                    </div>
                `;
            } finally {
                document.getElementById('refreshIndicator').classList.remove('loading');
                startCountdown();
            }
        }

        // Initial load
        loadDashboard();
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)
