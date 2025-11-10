"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Service Identity
    SERVICE_NAME: str = "image-processor"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"  # development, staging, production

    # Logging Configuration
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_JSON: bool = True    # JSON logs (prod) vs pretty console (dev)
    DEBUG: bool = False      # Enable debug mode features

    # Database
    DATABASE_PATH: str = "/data/processor.db"

    # Storage Backend Configuration
    STORAGE_BACKEND: str = "local"  # Options: "local" or "s3"
    STORAGE_PATH: str = "/data/storage"
    AWS_REGION: str = "eu-west-1"

    # Celery & Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Security
    JWT_SECRET_KEY: str = "change-this-in-production"
    JWT_ALGORITHM: str = "HS256"

    # Rate Limiting
    RATE_LIMIT_MAX_UPLOADS: int = 50
    RATE_LIMIT_WINDOW_MINUTES: int = 60

    # Upload Constraints
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_MIME_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp"]

    # Image Processing Configuration
    IMAGE_SIZES: dict = {
        "thumbnail": 150,
        "medium": 600,
        "large": 1200,
        "original": 4096
    }
    WEBP_QUALITY: int = 85

    # Celery Worker Configuration
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: List[str] = ["json"]
    CELERY_TIMEZONE: str = "UTC"
    CELERY_ENABLE_UTC: bool = True
    CELERY_TASK_TRACK_STARTED: bool = True
    CELERY_TASK_ACKS_LATE: bool = True  # Acknowledge after completion
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1  # One task at a time
    CELERY_WORKER_MAX_TASKS_PER_CHILD: int = 50  # Restart for memory cleanup

    @property
    def is_debug_mode(self) -> bool:
        """Check if application is in debug mode."""
        return self.DEBUG or self.LOG_LEVEL.upper() == "DEBUG"

    @property
    def use_json_logs(self) -> bool:
        """Determine if JSON logging should be used.

        In production, always use JSON logs.
        In development, allow override via LOG_JSON setting.
        """
        if self.ENVIRONMENT == "production":
            return True
        if self.DEBUG:
            return self.LOG_JSON
        return True

    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
