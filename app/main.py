"""Main FastAPI application for Image Processor Service."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from pathlib import Path

from app.core.config import settings
from app.core.logging_config import setup_logging, get_logger
from app.db.sqlite import get_db
from app.api.v1 import upload, retrieval, health, dashboard
from app.api.middleware import RequestLoggingMiddleware, PerformanceLoggingMiddleware
from app.api.exception_handlers import (
    http_exception_handler,
    validation_exception_handler,
    general_exception_handler,
)


# Initialize logging system (MUST be done before any logging calls)
setup_logging(debug=settings.is_debug_mode, json_logs=settings.use_json_logs)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events (startup and shutdown).

    Handles:
    - Database schema initialization
    - Logging startup information
    """
    # Startup
    logger.info(
        "application_startup",
        service=settings.SERVICE_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        debug_mode=settings.is_debug_mode,
        log_level=settings.LOG_LEVEL,
        storage_backend=settings.STORAGE_BACKEND,
    )

    # Initialize database schema
    db = get_db()
    await db.init_schema()
    logger.info("database_initialized", database_path=settings.DATABASE_PATH)

    yield

    # Shutdown
    logger.info("application_shutdown", graceful=True)


# Create FastAPI application
app = FastAPI(
    title=settings.SERVICE_NAME,
    description="Domain-agnostic image processing microservice with async workers",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Exception handlers for structured error logging
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Request logging and correlation ID middleware
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(PerformanceLoggingMiddleware, slow_request_threshold_ms=1000.0)

# CORS middleware configuration
# IMPORTANT: Configure appropriately for production!
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Replace with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(upload.router)
app.include_router(retrieval.router)
app.include_router(health.router)
app.include_router(dashboard.router)

# Mount static files for local storage backend
if settings.STORAGE_BACKEND == "local":
    storage_path = Path(settings.STORAGE_PATH)
    storage_path.mkdir(parents=True, exist_ok=True)

    app.mount(
        "/storage",
        StaticFiles(directory=settings.STORAGE_PATH),
        name="storage"
    )
    logger.info(
        "static_files_mounted",
        mount_path="/storage",
        directory=settings.STORAGE_PATH,
        backend=settings.STORAGE_BACKEND,
    )


@app.get("/")
async def root():
    """Root endpoint with service information.

    Returns:
        dict: Service metadata and useful links
    """
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "description": "Domain-agnostic image processing microservice",
        "documentation": "/docs",
        "health_check": "/api/v1/health",
        "dashboard": "/dashboard",
        "storage_backend": settings.STORAGE_BACKEND
    }


@app.get("/info")
async def service_info():
    """Detailed service configuration information.

    Returns:
        dict: Current service configuration (non-sensitive data)
    """
    return {
        "service": {
            "name": settings.SERVICE_NAME,
            "version": settings.VERSION
        },
        "storage": {
            "backend": settings.STORAGE_BACKEND,
            "region": settings.AWS_REGION if settings.STORAGE_BACKEND == "s3" else None
        },
        "processing": {
            "image_sizes": settings.IMAGE_SIZES,
            "webp_quality": settings.WEBP_QUALITY,
            "allowed_mime_types": settings.ALLOWED_MIME_TYPES
        },
        "limits": {
            "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB,
            "rate_limit_per_hour": settings.RATE_LIMIT_MAX_UPLOADS
        }
    }
