"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Service Identity
    SERVICE_NAME: str = "image-processor"
    VERSION: str = "1.0.0"

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

    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
