"""Local filesystem storage backend."""

import aiofiles
from pathlib import Path
from typing import BinaryIO

from app.core.logging_config import get_logger


logger = get_logger(__name__)


class LocalStorageBackend:
    """Local filesystem storage implementation.

    Stores files in a local directory structure organized by bucket and path.
    Suitable for development and single-server deployments.
    """

    def __init__(self, base_path: str):
        """Initialize local storage backend.

        Args:
            base_path: Root directory for file storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save(self, file: BinaryIO, bucket: str, path: str) -> str:
        """Save file to local filesystem.

        Args:
            file: Binary file object
            bucket: Bucket name (becomes subdirectory)
            path: File path within bucket

        Returns:
            str: Storage path in format "bucket/path"
        """
        full_path = self.base_path / bucket / path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        logger.debug(
            "local_storage_save_started",
            bucket=bucket,
            path=path,
            full_path=str(full_path),
        )

        try:
            # Write file in chunks for memory efficiency
            bytes_written = 0
            async with aiofiles.open(full_path, 'wb') as f:
                while chunk := file.read(8192):
                    await f.write(chunk)
                    bytes_written += len(chunk)

            logger.info(
                "local_storage_save_success",
                bucket=bucket,
                path=path,
                bytes_written=bytes_written,
                storage_path=f"{bucket}/{path}",
            )

            return f"{bucket}/{path}"

        except Exception as exc:
            logger.error(
                "local_storage_save_failed",
                bucket=bucket,
                path=path,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def load(self, bucket: str, path: str) -> bytes:
        """Load file from local filesystem.

        Args:
            bucket: Bucket name
            path: File path within bucket

        Returns:
            bytes: File contents
        """
        full_path = self.base_path / bucket / path

        logger.debug(
            "local_storage_load_started",
            bucket=bucket,
            path=path,
            full_path=str(full_path),
        )

        try:
            async with aiofiles.open(full_path, 'rb') as f:
                data = await f.read()

            logger.info(
                "local_storage_load_success",
                bucket=bucket,
                path=path,
                bytes_read=len(data),
            )

            return data

        except FileNotFoundError:
            logger.error(
                "local_storage_load_not_found",
                bucket=bucket,
                path=path,
                full_path=str(full_path),
            )
            raise
        except Exception as exc:
            logger.error(
                "local_storage_load_failed",
                bucket=bucket,
                path=path,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def delete(self, bucket: str, path: str) -> None:
        """Delete file from local filesystem.

        Args:
            bucket: Bucket name
            path: File path within bucket
        """
        full_path = self.base_path / bucket / path

        logger.debug(
            "local_storage_delete_started",
            bucket=bucket,
            path=path,
            full_path=str(full_path),
        )

        try:
            if full_path.exists():
                full_path.unlink()
                logger.info(
                    "local_storage_delete_success",
                    bucket=bucket,
                    path=path,
                )
            else:
                logger.warning(
                    "local_storage_delete_not_found",
                    bucket=bucket,
                    path=path,
                    full_path=str(full_path),
                )

        except Exception as exc:
            logger.error(
                "local_storage_delete_failed",
                bucket=bucket,
                path=path,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def get_url(self, bucket: str, path: str) -> str:
        """Get URL for static file serving.

        Args:
            bucket: Bucket name
            path: File path within bucket

        Returns:
            str: URL path for serving via FastAPI StaticFiles
        """
        return f"/storage/{bucket}/{path}"

    def get_local_path(self, bucket: str, path: str) -> Path:
        """Get absolute filesystem path.

        Args:
            bucket: Bucket name
            path: File path within bucket

        Returns:
            Path: Absolute path to file
        """
        return self.base_path / bucket / path
