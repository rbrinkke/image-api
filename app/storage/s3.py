"""AWS S3 storage backend."""

import aioboto3
from typing import BinaryIO


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
        async with self.session.client('s3', region_name=self.region) as s3:
            await s3.upload_fileobj(
                file, bucket, path,
                ExtraArgs={'ServerSideEncryption': 'AES256'}
            )
        return f"{bucket}/{path}"

    async def load(self, bucket: str, path: str) -> bytes:
        """Download file from S3.

        Args:
            bucket: S3 bucket name
            path: S3 object key

        Returns:
            bytes: File contents
        """
        async with self.session.client('s3', region_name=self.region) as s3:
            response = await s3.get_object(Bucket=bucket, Key=path)
            return await response['Body'].read()

    async def delete(self, bucket: str, path: str) -> None:
        """Delete file from S3.

        Args:
            bucket: S3 bucket name
            path: S3 object key
        """
        async with self.session.client('s3', region_name=self.region) as s3:
            await s3.delete_object(Bucket=bucket, Key=path)

    def get_url(self, bucket: str, path: str, expires_in: int = 3600) -> str:
        """Generate presigned URL for S3 object.

        Args:
            bucket: S3 bucket name
            path: S3 object key
            expires_in: URL expiration time in seconds (default: 1 hour)

        Returns:
            str: Presigned URL for direct access
        """
        import boto3
        s3 = boto3.client('s3', region_name=self.region)
        return s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': path},
            ExpiresIn=expires_in
        )
