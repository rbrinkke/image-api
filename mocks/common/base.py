"""Base FastAPI application factory for all mocks."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Dict, Any, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def create_mock_app(
    title: str,
    description: str,
    version: str = "1.0.0",
    enable_cors: bool = True,
    cors_origins: Optional[list] = None
) -> FastAPI:
    """Factory function for creating standardized mock FastAPI apps.

    Provides consistent configuration across all mock servers:
    - CORS middleware for development
    - Standard health check endpoint
    - OpenAPI documentation
    - Structured logging

    Args:
        title: API title
        description: API description
        version: API version
        enable_cors: Enable CORS middleware
        cors_origins: Allowed CORS origins (default: ["*"])

    Returns:
        Configured FastAPI application with health endpoint

    Example:
        >>> app = create_mock_app(
        ...     title="S3 Mock API",
        ...     description="AWS S3-compatible mock server",
        ...     version="1.0.0"
        ... )
    """
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        docs_url="/docs",
        redoc_url="/redoc"
    )

    if enable_cors:
        origins = cors_origins if cors_origins is not None else ["*"]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/health")
    async def health_check() -> Dict[str, Any]:
        """Standard health check endpoint.

        Returns:
            Health status with service name, version, and timestamp
        """
        return {
            "status": "healthy",
            "service": title,
            "timestamp": datetime.utcnow().isoformat(),
            "version": version
        }

    # Log startup
    logger = logging.getLogger(title)
    logger.info(f"{title} v{version} initialized")

    return app
