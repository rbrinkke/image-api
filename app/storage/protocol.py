"""Storage backend protocol definition."""

from typing import Protocol, BinaryIO


class StorageBackend(Protocol):
    """Protocol defining the interface for storage backends.

    This allows seamless switching between local filesystem and cloud storage
    without changing application code.
    """

    async def save(self, file: BinaryIO, bucket: str, path: str) -> str:
        """Save file to storage.

        Args:
            file: Binary file object to save
            bucket: Storage bucket/container name
            path: Relative path within bucket

        Returns:
            str: Storage path identifier
        """
        ...

    async def load(self, bucket: str, path: str) -> bytes:
        """Load file from storage.

        Args:
            bucket: Storage bucket/container name
            path: Relative path within bucket

        Returns:
            bytes: File contents
        """
        ...

    async def delete(self, bucket: str, path: str) -> None:
        """Delete file from storage.

        Args:
            bucket: Storage bucket/container name
            path: Relative path within bucket
        """
        ...

    async def get_url(self, bucket: str, path: str) -> str:
        """Get access URL for a file.

        Args:
            bucket: Storage bucket/container name
            path: Relative path within bucket

        Returns:
            str: URL to access the file
        """
        ...
