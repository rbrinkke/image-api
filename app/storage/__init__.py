"""Storage abstraction layer for local and cloud storage."""

from functools import lru_cache
from app.core.config import settings
from .protocol import StorageBackend
from .local import LocalStorageBackend
# S3 backend imported lazily when needed


@lru_cache()
def get_storage() -> StorageBackend:
    """Factory function for storage backend.

    Returns storage backend based on STORAGE_BACKEND configuration.

    Returns:
        StorageBackend: Configured storage backend instance

    Raises:
        ValueError: If unknown storage backend is configured
    """
    if settings.STORAGE_BACKEND == "local":
        return LocalStorageBackend(settings.STORAGE_PATH)
    elif settings.STORAGE_BACKEND == "s3":
        # Lazy import to avoid requiring aioboto3 when using local storage
        from .s3 import S3StorageBackend
        return S3StorageBackend(settings.AWS_REGION)
    else:
        raise ValueError(f"Unknown storage backend: {settings.STORAGE_BACKEND}")


__all__ = ["get_storage", "StorageBackend", "LocalStorageBackend"]
