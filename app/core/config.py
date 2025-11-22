"""Application configuration using Pydantic Settings."""

import re
from pydantic import BaseModel, field_validator, model_validator
from pydantic_settings import BaseSettings
from typing import List, Optional
import os


class ImageSizesConfig(BaseModel):
    """Type-safe configuration for image variant sizes.

    Each field represents a variant name and its maximum dimension in pixels.
    This prevents runtime errors from misconfigured IMAGE_SIZES in environment.

    Example:
        thumbnail=150 means the thumbnail variant will be max 150x150px
        while maintaining the original aspect ratio.
    """
    thumbnail: int = 150
    medium: int = 600
    large: int = 1200
    original: int = 4096

    @field_validator('thumbnail', 'medium', 'large', 'original')
    @classmethod
    def validate_dimension(cls, v: int) -> int:
        """Ensure dimensions are positive and reasonable."""
        if v <= 0:
            raise ValueError(f"Image dimension must be positive, got {v}")
        if v > 8192:
            raise ValueError(f"Image dimension too large (max 8192), got {v}")
        return v


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
    # Use a local file path relative to the project root for development default
    DATABASE_PATH: str = os.path.join(os.getcwd(), "processor.db")

    # Storage Backend Configuration
    STORAGE_BACKEND: str = "local"  # Options: "local" or "s3"
    STORAGE_PATH: str = os.path.join(os.getcwd(), "storage")

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
    # Type-safe image variant configuration using nested Pydantic model
    IMAGE_SIZES: ImageSizesConfig = ImageSizesConfig()
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

    @field_validator('AWS_S3_BUCKET_NAME')
    @classmethod
    def validate_s3_bucket_name(cls, v: str) -> str:
        """Validate S3 bucket name follows AWS naming conventions.

        Rules:
        - 3-63 characters long
        - Lowercase letters, numbers, hyphens, and dots only
        - Must start and end with a letter or number
        - No consecutive dots
        - Not formatted as an IP address
        """
        if not v:  # Allow empty for local storage backend
            return v

        if not 3 <= len(v) <= 63:
            raise ValueError(f"S3 bucket name must be 3-63 characters long, got {len(v)}")

        # Check for valid characters and format
        if not re.match(r'^[a-z0-9][a-z0-9.-]*[a-z0-9]$', v):
            raise ValueError(
                f"S3 bucket name '{v}' must start/end with letter or number, "
                "and contain only lowercase letters, numbers, hyphens, and dots"
            )

        # Check for consecutive dots
        if '..' in v:
            raise ValueError("S3 bucket name cannot contain consecutive dots")

        # Check if it looks like an IP address
        if re.match(r'^\d+\.\d+\.\d+\.\d+$', v):
            raise ValueError("S3 bucket name cannot be formatted as an IP address")

        return v

    @field_validator('AWS_ENDPOINT_URL')
    @classmethod
    def validate_endpoint_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate AWS endpoint URL format if provided."""
        if v is None or v == "":
            return None

        # Basic URL validation
        if not re.match(r'^https?://.+', v):
            raise ValueError(
                f"AWS_ENDPOINT_URL must start with http:// or https://, got '{v}'"
            )

        return v

    @model_validator(mode='after')
    def validate_s3_configuration(self):
        """Ensure S3 backend has required configuration."""
        if self.STORAGE_BACKEND == "s3":
            if not self.AWS_S3_BUCKET_NAME:
                raise ValueError(
                    "AWS_S3_BUCKET_NAME must be set when STORAGE_BACKEND=s3"
                )
            if not self.AWS_REGION:
                raise ValueError(
                    "AWS_REGION must be set when STORAGE_BACKEND=s3"
                )
        return self

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

# Updated: 2025-11-18 22:01 UTC - Production-ready code
