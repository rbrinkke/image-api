"""AWS S3 storage backend."""

import aioboto3
from typing import BinaryIO, Optional

from app.core.logging_config import get_logger


logger = get_logger(__name__)


class S3StorageBackend:
    """AWS S3 storage implementation using a single bucket with prefixes.

    This implementation uses a single physical S3 bucket and treats the logical
    "bucket" parameter (e.g., "org-123/groups/abc") as a prefix within that bucket.

    This is the industry-standard approach for multi-tenant S3 storage, avoiding
    the overhead of managing thousands of separate buckets.

    Supports both AWS S3 and S3-compatible services (e.g., MinIO) via endpoint_url.
    """

    def __init__(
        self,
        region: str,
        bucket_name: str,
        endpoint_url: Optional[str] = None
    ):
        """Initialize S3 storage backend.

        Args:
            region: AWS region name (e.g., "eu-west-1")
            bucket_name: Physical S3 bucket name (e.g., "image-api-prod")
            endpoint_url: Optional S3-compatible endpoint (e.g., "http://minio:9000")
        """
        self.session = aioboto3.Session()
        self.region = region
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url

        logger.info(
            "s3_storage_backend_initialized",
            region=self.region,
            bucket_name=self.bucket_name,
            endpoint_url=self.endpoint_url,
            s3_compatible=bool(endpoint_url),
        )

    def _get_s3_client(self):
        """Create S3 client with optional custom endpoint.

        Returns:
            aioboto3 S3 client resource manager
        """
        return self.session.client(
            's3',
            region_name=self.region,
            endpoint_url=self.endpoint_url
        )

    async def save(self, file: BinaryIO, bucket: str, path: str) -> str:
        """Upload file to S3.

        Args:
            file: Binary file object
            bucket: Logical bucket (used as prefix, e.g., "org-123/groups/abc")
            path: File path within the logical bucket (e.g., "processed/medium/uuid.webp")

        Returns:
            str: Storage path in format "bucket/path" (logical path preserved)
        """
        # Combine logical bucket and path to create the S3 object key
        s3_key = f"{bucket}/{path}"
        storage_path = s3_key

        logger.debug(
            "s3_storage_save_started",
            physical_bucket=self.bucket_name,
            logical_bucket=bucket,
            path=path,
            s3_key=s3_key,
            region=self.region,
        )

        try:
            async with self._get_s3_client() as s3:
                await s3.upload_fileobj(
                    file,
                    self.bucket_name,  # Use physical bucket name
                    s3_key,            # Use combined key as object path
                    ExtraArgs={'ServerSideEncryption': 'AES256'}
                )

            logger.info(
                "s3_storage_save_success",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                region=self.region,
                encryption="AES256",
                storage_path=storage_path,
            )

            return storage_path

        except Exception as exc:
            logger.error(
                "s3_storage_save_failed",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                region=self.region,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def load(self, bucket: str, path: str) -> bytes:
        """Download file from S3.

        Args:
            bucket: Logical bucket (used as prefix, e.g., "org-123/groups/abc")
            path: File path within the logical bucket

        Returns:
            bytes: File contents
        """
        # Combine logical bucket and path to create the S3 object key
        s3_key = f"{bucket}/{path}"

        logger.debug(
            "s3_storage_load_started",
            physical_bucket=self.bucket_name,
            logical_bucket=bucket,
            path=path,
            s3_key=s3_key,
            region=self.region,
        )

        try:
            async with self._get_s3_client() as s3:
                response = await s3.get_object(Bucket=self.bucket_name, Key=s3_key)
                data = await response['Body'].read()

            logger.info(
                "s3_storage_load_success",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                region=self.region,
                bytes_read=len(data),
            )

            return data

        except Exception as exc:
            logger.error(
                "s3_storage_load_failed",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                region=self.region,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise

    async def delete(self, bucket: str, path: str) -> None:
        """Delete file from S3.

        Args:
            bucket: Logical bucket (used as prefix, e.g., "org-123/groups/abc")
            path: File path within the logical bucket
        """
        # Combine logical bucket and path to create the S3 object key
        s3_key = f"{bucket}/{path}"

        logger.debug(
            "s3_storage_delete_started",
            physical_bucket=self.bucket_name,
            logical_bucket=bucket,
            path=path,
            s3_key=s3_key,
            region=self.region,
        )

        try:
            async with self._get_s3_client() as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=s3_key)

            logger.info(
                "s3_storage_delete_success",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                region=self.region,
            )

        except Exception as exc:
            logger.error(
                "s3_storage_delete_failed",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
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
            bucket: Logical bucket (used as prefix, e.g., "org-123/groups/abc")
            path: File path within the logical bucket
            expires_in: URL expiration time in seconds (default: 1 hour)

        Returns:
            str: Presigned URL for direct access
        """
        # Combine logical bucket and path to create the S3 object key
        s3_key = f"{bucket}/{path}"

        logger.debug(
            "s3_presigned_url_generation_started",
            physical_bucket=self.bucket_name,
            logical_bucket=bucket,
            path=path,
            s3_key=s3_key,
            expires_in=expires_in,
        )

        try:
            async with self._get_s3_client() as s3:
                url = await s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket_name, 'Key': s3_key},
                    ExpiresIn=expires_in
                )

            logger.info(
                "s3_presigned_url_generated",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                expires_in=expires_in,
            )

            return url

        except Exception as exc:
            logger.error(
                "s3_presigned_url_generation_failed",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            raise
