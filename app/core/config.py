"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from typing import List, Optional


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

    # S3 Storage Configuration
    AWS_REGION: str = "eu-west-1"
    AWS_S3_BUCKET_NAME: str = "image-api-dev"  # Physical S3 bucket name
    AWS_ENDPOINT_URL: Optional[str] = None  # For MinIO or S3-compatible services

    # Celery & Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Security - OAuth 2.0 Resource Server Configuration
    # The image-api acts as an OAuth 2.0 Resource Server
    # Tokens are validated locally using the auth-api's public JWKS endpoint

    # Auth API Configuration
    AUTH_API_ISSUER_URL: str = "http://auth-api:8000"
    AUTH_API_JWKS_URL: str = "http://auth-api:8000/.well-known/jwks.json"

    # Expected audience for this service
    AUTH_API_AUDIENCE: str = "image-api"

    # JWT algorithm (RS256 for asymmetric key validation)
    JWT_ALGORITHM: str = "RS256"

    # JWKS caching (in seconds) - how often to refresh public keys
    JWKS_CACHE_TTL: int = 3600  # 1 hour

    # Backward compatibility - old symmetric key (deprecated, used for testing only)
    JWT_SECRET_KEY: str = "change-this-in-production"  # DEPRECATED: Only for testing

    # Auth-API Integration for distributed authorization
    AUTH_API_URL: str = "http://auth-api:8000"
    AUTH_API_TIMEOUT: int = 5
    AUTH_API_CHECK_ENDPOINT: str = "/api/v1/authorization/check"

    # Authorization Cache
    AUTH_CACHE_ENABLED: bool = True
    AUTH_CACHE_TTL_ALLOWED: int = 60  # Cache allowed permissions for 60s
    AUTH_CACHE_TTL_DENIED: int = 120  # Cache denied permissions for 120s

    # Circuit Breaker
    CIRCUIT_BREAKER_ENABLED: bool = True
    CIRCUIT_BREAKER_THRESHOLD: int = 5  # Open after 5 consecutive failures
    CIRCUIT_BREAKER_TIMEOUT: int = 60  # Stay open for 60s
    AUTH_FAIL_OPEN: bool = False  # Fail-closed: deny access when auth-api is down

    # Bucket Validation
    BUCKET_VALIDATION_STRICT: bool = True  # Enforce strict bucket format validation

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
