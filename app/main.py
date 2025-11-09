"""Main FastAPI application for Image Processor Service."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from app.core.config import settings
from app.db.sqlite import get_db
from app.api.v1 import upload, retrieval, health


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events (startup and shutdown).

    Handles:
    - Database schema initialization
    - Logging startup information
    """
    # Startup
    logger.info(f"Starting {settings.SERVICE_NAME} v{settings.VERSION}")
    logger.info(f"Storage backend: {settings.STORAGE_BACKEND}")

    # Initialize database schema
    db = get_db()
    await db.init_schema()
    logger.info("Database initialized successfully")

    yield

    # Shutdown
    logger.info("Shutting down gracefully")


# Create FastAPI application
app = FastAPI(
    title=settings.SERVICE_NAME,
    description="Domain-agnostic image processing microservice with async workers",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

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

# Mount static files for local storage backend
if settings.STORAGE_BACKEND == "local":
    storage_path = Path(settings.STORAGE_PATH)
    storage_path.mkdir(parents=True, exist_ok=True)

    app.mount(
        "/storage",
        StaticFiles(directory=settings.STORAGE_PATH),
        name="storage"
    )
    logger.info(f"Static files mounted at /storage (path: {settings.STORAGE_PATH})")


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
