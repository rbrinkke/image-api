"""Local filesystem storage backend."""

import aiofiles
from pathlib import Path
from typing import BinaryIO


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

        # Write file in chunks for memory efficiency
        async with aiofiles.open(full_path, 'wb') as f:
            while chunk := file.read(8192):
                await f.write(chunk)

        return f"{bucket}/{path}"

    async def load(self, bucket: str, path: str) -> bytes:
        """Load file from local filesystem.

        Args:
            bucket: Bucket name
            path: File path within bucket

        Returns:
            bytes: File contents
        """
        full_path = self.base_path / bucket / path
        async with aiofiles.open(full_path, 'rb') as f:
            return await f.read()

    async def delete(self, bucket: str, path: str) -> None:
        """Delete file from local filesystem.

        Args:
            bucket: Bucket name
            path: File path within bucket
        """
        full_path = self.base_path / bucket / path
        if full_path.exists():
            full_path.unlink()

    def get_url(self, bucket: str, path: str) -> str:
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
