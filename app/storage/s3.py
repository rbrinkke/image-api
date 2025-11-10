"""AWS S3 storage backend."""

import aioboto3
from typing import BinaryIO

from app.core.logging_config import get_logger


logger = get_logger(__name__)


class S3StorageBackend:
    """AWS S3 storage implementation.

    Provides cloud storage with server-side encryption and presigned URLs.
    Suitable for production deployments requiring scalability and reliability.
    """

    def __init__(self, region: str = "eu-west-1"):
        """Initialize S3 storage backend.

        Args:
            region: AWS region name
        """
        self.session = aioboto3.Session()
        self.region = region

    async def save(self, file: BinaryIO, bucket: str, path: str) -> str:
        """Upload file to S3.

        Args:
            file: Binary file object
            bucket: S3 bucket name
            path: S3 object key

        Returns:
            str: Storage path in format "bucket/path"
        """
        logger.debug(
            "s3_storage_save_started",
            bucket=bucket,
            path=path,
            region=self.region,
        )

        try:
            async with self.session.client('s3', region_name=self.region) as s3:
                await s3.upload_fileobj(
                    file, bucket, path,
                    ExtraArgs={'ServerSideEncryption': 'AES256'}
                )

            logger.info(
                "s3_storage_save_success",
                bucket=bucket,
                path=path,
                region=self.region,
                encryption="AES256",
                storage_path=f"{bucket}/{path}",
            )

            return f"{bucket}/{path}"

        except Exception as exc:
            logger.error(
                "s3_storage_save_failed",
                bucket=bucket,
                path=path,
                region=self.region,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def load(self, bucket: str, path: str) -> bytes:
        """Download file from S3.

        Args:
            bucket: S3 bucket name
            path: S3 object key

        Returns:
            bytes: File contents
        """
        logger.debug(
            "s3_storage_load_started",
            bucket=bucket,
            path=path,
            region=self.region,
        )

        try:
            async with self.session.client('s3', region_name=self.region) as s3:
                response = await s3.get_object(Bucket=bucket, Key=path)
                data = await response['Body'].read()

            logger.info(
                "s3_storage_load_success",
                bucket=bucket,
                path=path,
                region=self.region,
                bytes_read=len(data),
            )

            return data

        except Exception as exc:
            logger.error(
                "s3_storage_load_failed",
                bucket=bucket,
                path=path,
                region=self.region,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def delete(self, bucket: str, path: str) -> None:
        """Delete file from S3.

        Args:
            bucket: S3 bucket name
            path: S3 object key
        """
        logger.debug(
            "s3_storage_delete_started",
            bucket=bucket,
            path=path,
            region=self.region,
        )

        try:
            async with self.session.client('s3', region_name=self.region) as s3:
                await s3.delete_object(Bucket=bucket, Key=path)

            logger.info(
                "s3_storage_delete_success",
                bucket=bucket,
                path=path,
                region=self.region,
            )

        except Exception as exc:
            logger.error(
                "s3_storage_delete_failed",
                bucket=bucket,
                path=path,
                region=self.region,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def get_url(self, bucket: str, path: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for S3 object.

        Uses async aioboto3 for consistent async implementation.

        Args:
            bucket: S3 bucket name
            path: S3 object key
            expires_in: URL expiration time in seconds (default: 1 hour)

        Returns:
            str: Presigned URL for direct access
        """
        logger.debug(
            "s3_presigned_url_generation_started",
            bucket=bucket,
            path=path,
            expires_in=expires_in,
        )

        try:
            async with self.session.client('s3', region_name=self.region) as s3:
                url = await s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket, 'Key': path},
                    ExpiresIn=expires_in
                )

            logger.info(
                "s3_presigned_url_generated",
                bucket=bucket,
                path=path,
                expires_in=expires_in,
            )

            return url

        except Exception as exc:
            logger.error(
                "s3_presigned_url_generation_failed",
                bucket=bucket,
                path=path,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise
