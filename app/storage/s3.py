"""AWS S3 storage backend."""

import aioboto3
from typing import BinaryIO, Optional
from botocore.exceptions import ClientError, BotoCoreError

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

    @staticmethod
    def _normalize_path(bucket: str, path: str) -> str:
        """Normalize and validate S3 object key.

        Args:
            bucket: Logical bucket (prefix)
            path: File path

        Returns:
            str: Normalized S3 object key

        Raises:
            ValueError: If bucket or path are invalid
        """
        # Validate inputs
        if not bucket or not bucket.strip():
            raise ValueError("Bucket parameter cannot be empty")
        if not path or not path.strip():
            raise ValueError("Path parameter cannot be empty")

        # Normalize: strip leading/trailing slashes and whitespace
        bucket = bucket.strip().strip('/')
        path = path.strip().strip('/')

        # Additional validation
        if not bucket:
            raise ValueError("Bucket parameter contains only whitespace or slashes")
        if not path:
            raise ValueError("Path parameter contains only whitespace or slashes")

        # Prevent path traversal attacks
        if '..' in bucket or '..' in path:
            raise ValueError("Path traversal patterns (..) are not allowed")

        # Combine into S3 key
        s3_key = f"{bucket}/{path}"

        # Validate final key length (S3 limit is 1024 bytes)
        if len(s3_key.encode('utf-8')) > 1024:
            raise ValueError(
                f"S3 object key too long ({len(s3_key.encode('utf-8'))} bytes, max 1024)"
            )

        return s3_key

    def _handle_s3_error(
        self,
        exc: Exception,
        operation: str,
        bucket: str,
        path: str
    ) -> Exception:
        """Standardize S3 error handling with detailed context.

        Args:
            exc: Original exception
            operation: Operation being performed (e.g., 'upload', 'download')
            bucket: Logical bucket
            path: File path

        Returns:
            Exception: Enriched exception with context
        """
        error_context = {
            "operation": operation,
            "logical_bucket": bucket,
            "path": path,
            "physical_bucket": self.bucket_name,
        }

        if isinstance(exc, ClientError):
            error_code = exc.response.get('Error', {}).get('Code', 'Unknown')
            error_message = exc.response.get('Error', {}).get('Message', str(exc))
            error_context.update({
                "error_code": error_code,
                "error_message": error_message,
                "http_status": exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode'),
            })

            # Specific error handling
            if error_code == 'NoSuchBucket':
                return FileNotFoundError(
                    f"S3 bucket '{self.bucket_name}' does not exist. "
                    f"Please create the bucket before using S3 storage. Context: {error_context}"
                )
            elif error_code == 'NoSuchKey':
                return FileNotFoundError(
                    f"Object not found in S3: {bucket}/{path}. Context: {error_context}"
                )
            elif error_code in ('AccessDenied', '403'):
                return PermissionError(
                    f"Access denied to S3 bucket '{self.bucket_name}'. "
                    f"Check AWS credentials and IAM permissions. Context: {error_context}"
                )

        elif isinstance(exc, BotoCoreError):
            error_context["botocore_error"] = type(exc).__name__

        # Return generic exception with enriched message
        return type(exc)(f"{operation.capitalize()} failed: {str(exc)}. Context: {error_context}")

    async def save(self, file: BinaryIO, bucket: str, path: str) -> str:
        """Upload file to S3.

        Args:
            file: Binary file object
            bucket: Logical bucket (used as prefix, e.g., "org-123/groups/abc")
            path: File path within the logical bucket (e.g., "processed/medium/uuid.webp")

        Returns:
            str: Storage path in format "bucket/path" (logical path preserved)

        Raises:
            ValueError: If bucket or path are invalid
            FileNotFoundError: If S3 bucket doesn't exist
            PermissionError: If access is denied
        """
        try:
            # Normalize and validate the S3 key
            s3_key = self._normalize_path(bucket, path)
            storage_path = s3_key

            logger.debug(
                "s3_storage_save_started",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                region=self.region,
            )

            # Ensure file pointer is at the beginning
            if hasattr(file, 'seek'):
                file.seek(0)

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

        except (ValueError, FileNotFoundError, PermissionError):
            # Re-raise validation and S3-specific errors as-is
            raise
        except Exception as exc:
            logger.error(
                "s3_storage_save_failed",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                region=self.region,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            # Convert to enriched exception
            raise self._handle_s3_error(exc, "upload", bucket, path)

    async def load(self, bucket: str, path: str) -> bytes:
        """Download file from S3.

        Args:
            bucket: Logical bucket (used as prefix, e.g., "org-123/groups/abc")
            path: File path within the logical bucket

        Returns:
            bytes: File contents

        Raises:
            ValueError: If bucket or path are invalid
            FileNotFoundError: If object doesn't exist
            PermissionError: If access is denied
        """
        try:
            # Normalize and validate the S3 key
            s3_key = self._normalize_path(bucket, path)

            logger.debug(
                "s3_storage_load_started",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                region=self.region,
            )

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

        except (ValueError, FileNotFoundError, PermissionError):
            # Re-raise validation and S3-specific errors as-is
            raise
        except Exception as exc:
            logger.error(
                "s3_storage_load_failed",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                region=self.region,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            # Convert to enriched exception
            raise self._handle_s3_error(exc, "download", bucket, path)

    async def delete(self, bucket: str, path: str) -> None:
        """Delete file from S3.

        Args:
            bucket: Logical bucket (used as prefix, e.g., "org-123/groups/abc")
            path: File path within the logical bucket

        Raises:
            ValueError: If bucket or path are invalid
            PermissionError: If access is denied

        Note:
            S3 delete operations are idempotent - deleting a non-existent object
            succeeds without error. This is AWS S3 behavior by design.
        """
        try:
            # Normalize and validate the S3 key
            s3_key = self._normalize_path(bucket, path)

            logger.debug(
                "s3_storage_delete_started",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                region=self.region,
            )

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

        except (ValueError, PermissionError):
            # Re-raise validation and S3-specific errors as-is
            raise
        except Exception as exc:
            logger.error(
                "s3_storage_delete_failed",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                region=self.region,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            # Convert to enriched exception
            raise self._handle_s3_error(exc, "delete", bucket, path)

    async def get_url(self, bucket: str, path: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for S3 object.

        Uses async aioboto3 for consistent async implementation.

        Args:
            bucket: Logical bucket (used as prefix, e.g., "org-123/groups/abc")
            path: File path within the logical bucket
            expires_in: URL expiration time in seconds (default: 1 hour, max: 7 days)

        Returns:
            str: Presigned URL for direct access

        Raises:
            ValueError: If bucket, path, or expires_in are invalid
            PermissionError: If access is denied
        """
        # Validate expires_in parameter
        if expires_in < 1:
            raise ValueError("expires_in must be at least 1 second")
        if expires_in > 604800:  # 7 days in seconds
            raise ValueError("expires_in cannot exceed 604800 seconds (7 days)")

        try:
            # Normalize and validate the S3 key
            s3_key = self._normalize_path(bucket, path)

            logger.debug(
                "s3_presigned_url_generation_started",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                s3_key=s3_key,
                expires_in=expires_in,
            )

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

        except (ValueError, PermissionError):
            # Re-raise validation and S3-specific errors as-is
            raise
        except Exception as exc:
            logger.error(
                "s3_presigned_url_generation_failed",
                physical_bucket=self.bucket_name,
                logical_bucket=bucket,
                path=path,
                region=self.region,
                error_type=type(exc).__name__,
                error=str(exc),
                exc_info=True,
            )
            # Convert to enriched exception
            raise self._handle_s3_error(exc, "presigned_url_generation", bucket, path)

# Updated: 2025-11-18 22:01 UTC - Production-ready code
