"""
S3-Compatible Mock Server
==========================

AWS S3-compatible mock server for testing without AWS dependencies.
Implements core S3 operations: upload, download, delete, presigned URLs.

Usage:
    python s3_mock.py
    # or
    uvicorn s3_mock:app --reload --port 9000

Endpoints:
    PUT /{bucket}/{key:path}          - Upload object
    GET /{bucket}/{key:path}          - Download object
    DELETE /{bucket}/{key:path}       - Delete object
    HEAD /{bucket}/{key:path}         - Get object metadata
    POST /presigned-url               - Generate presigned URL
    GET /admin/buckets                - List all buckets (admin)
    GET /admin/objects/{bucket}       - List objects in bucket (admin)
    DELETE /admin/reset               - Clear all data (admin)
    GET /health                       - Health check

Configuration:
    PORT: Server port (default: 9000)
    PRESIGNED_URL_BASE: Base URL for presigned URLs (default: http://localhost:9000)
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Path, Query, Header, Response
from fastapi.responses import JSONResponse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mocks.common.base import create_mock_app
from mocks.common.errors import NotFoundError, ValidationError
from typing import Dict, Optional
from datetime import datetime, timedelta
import hashlib
import io
import logging

# Configure logging
logger = logging.getLogger("S3Mock")

# In-memory storage: {bucket_name: {object_key: object_data}}
buckets: Dict[str, Dict[str, bytes]] = {}
object_metadata: Dict[str, Dict[str, Dict]] = {}  # {bucket: {key: metadata}}

# Configuration
PRESIGNED_URL_BASE = os.getenv("PRESIGNED_URL_BASE", "http://localhost:9000")

# Initialize FastAPI app
app = create_mock_app(
    title="S3 Mock API",
    description="AWS S3-compatible mock server for testing image storage",
    version="1.0.0"
)


def ensure_bucket_exists(bucket: str) -> None:
    """Ensure bucket exists, create if not."""
    if bucket not in buckets:
        buckets[bucket] = {}
        object_metadata[bucket] = {}
        logger.info(f"Created bucket: {bucket}")


def calculate_etag(content: bytes) -> str:
    """Calculate ETag (MD5 hash) for object."""
    return hashlib.md5(content).hexdigest()


@app.put("/{bucket}/{key:path}")
async def put_object(
    bucket: str = Path(..., description="Bucket name"),
    key: str = Path(..., description="Object key (path)"),
    file: UploadFile = File(...),
    content_type: Optional[str] = Header(None),
    x_amz_server_side_encryption: Optional[str] = Header(None, alias="x-amz-server-side-encryption")
):
    """Upload object to S3 bucket (PutObject).

    Args:
        bucket: Target bucket name
        key: Object key (path within bucket)
        file: File upload
        content_type: Content-Type header
        x_amz_server_side_encryption: Server-side encryption (AES256)

    Returns:
        204 No Content with ETag header
    """
    ensure_bucket_exists(bucket)

    # Read file content
    content = await file.read()
    etag = calculate_etag(content)

    # Store object
    buckets[bucket][key] = content
    object_metadata[bucket][key] = {
        "size": len(content),
        "last_modified": datetime.utcnow(),
        "etag": etag,
        "content_type": content_type or "application/octet-stream",
        "server_side_encryption": x_amz_server_side_encryption or "AES256",
        "storage_class": "STANDARD"
    }

    logger.info(f"Uploaded object: {bucket}/{key} ({len(content)} bytes)")

    return Response(
        status_code=200,
        headers={
            "ETag": f'"{etag}"',
            "x-amz-server-side-encryption": x_amz_server_side_encryption or "AES256"
        }
    )


@app.get("/{bucket}/{key:path}")
async def get_object(
    bucket: str = Path(..., description="Bucket name"),
    key: str = Path(..., description="Object key"),
    x_amz_signature: Optional[str] = Query(None, alias="X-Amz-Signature"),
    x_amz_expires: Optional[int] = Query(None, alias="X-Amz-Expires")
):
    """Download object from S3 bucket (GetObject).

    Supports both direct access and presigned URL access.

    Args:
        bucket: Source bucket name
        key: Object key
        x_amz_signature: Presigned URL signature (optional)
        x_amz_expires: Presigned URL expiration (optional)

    Returns:
        Binary file content

    Raises:
        404: Object not found
    """
    if bucket not in buckets or key not in buckets[bucket]:
        raise NotFoundError("Object", f"{bucket}/{key}")

    content = buckets[bucket][key]
    metadata = object_metadata[bucket][key]

    logger.info(f"Downloaded object: {bucket}/{key} ({len(content)} bytes)")

    return Response(
        content=content,
        media_type=metadata.get("content_type", "application/octet-stream"),
        headers={
            "ETag": f'"{metadata["etag"]}"',
            "Last-Modified": metadata["last_modified"].strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "Content-Length": str(len(content))
        }
    )


@app.delete("/{bucket}/{key:path}")
async def delete_object(
    bucket: str = Path(..., description="Bucket name"),
    key: str = Path(..., description="Object key")
):
    """Delete object from S3 bucket (DeleteObject).

    S3 DeleteObject returns 204 even if object doesn't exist (idempotent).

    Args:
        bucket: Target bucket name
        key: Object key

    Returns:
        204 No Content
    """
    if bucket in buckets and key in buckets[bucket]:
        del buckets[bucket][key]
        del object_metadata[bucket][key]
        logger.info(f"Deleted object: {bucket}/{key}")

    return Response(status_code=204)


@app.head("/{bucket}/{key:path}")
async def head_object(
    bucket: str = Path(..., description="Bucket name"),
    key: str = Path(..., description="Object key")
):
    """Get object metadata without downloading (HeadObject).

    Args:
        bucket: Bucket name
        key: Object key

    Returns:
        Empty response with metadata headers

    Raises:
        404: Object not found
    """
    if bucket not in buckets or key not in buckets[bucket]:
        raise NotFoundError("Object", f"{bucket}/{key}")

    metadata = object_metadata[bucket][key]

    return Response(
        status_code=200,
        headers={
            "Content-Length": str(metadata["size"]),
            "ETag": f'"{metadata["etag"]}"',
            "Last-Modified": metadata["last_modified"].strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "Content-Type": metadata["content_type"],
            "x-amz-server-side-encryption": metadata.get("server_side_encryption", "AES256")
        }
    )


@app.post("/presigned-url")
async def generate_presigned_url(
    bucket: str = Query(..., description="Bucket name"),
    key: str = Query(..., description="Object key"),
    expires_in: int = Query(3600, description="Expiration time in seconds", ge=1, le=604800)
):
    """Generate presigned URL for object access.

    Compatible with aioboto3 generate_presigned_url().

    Args:
        bucket: Bucket name
        key: Object key
        expires_in: URL expiration in seconds (1 second to 7 days)

    Returns:
        Presigned URL and expiration details

    Raises:
        404: Object not found
    """
    if bucket not in buckets or key not in buckets[bucket]:
        raise NotFoundError("Object", f"{bucket}/{key}")

    # Generate mock signature
    expiration = datetime.utcnow() + timedelta(seconds=expires_in)
    signature_input = f"{bucket}/{key}/{expiration.isoformat()}"
    signature = hashlib.sha256(signature_input.encode()).hexdigest()[:16]

    # Construct presigned URL
    presigned_url = f"{PRESIGNED_URL_BASE}/{bucket}/{key}?X-Amz-Signature={signature}&X-Amz-Expires={expires_in}"

    logger.info(f"Generated presigned URL for {bucket}/{key} (expires in {expires_in}s)")

    return {
        "url": presigned_url,
        "expires_at": expiration.isoformat(),
        "expires_in": expires_in
    }


@app.get("/admin/buckets")
async def list_buckets():
    """List all buckets and their statistics (admin endpoint).

    Returns:
        Dictionary of buckets with object counts and total sizes
    """
    return {
        bucket: {
            "object_count": len(objects),
            "total_size": sum(len(obj) for obj in objects.values()),
            "total_size_mb": round(sum(len(obj) for obj in objects.values()) / 1024 / 1024, 2),
            "keys": list(objects.keys())
        }
        for bucket, objects in buckets.items()
    }


@app.get("/admin/objects/{bucket}")
async def list_objects(bucket: str = Path(..., description="Bucket name")):
    """List all objects in a bucket (admin endpoint).

    Args:
        bucket: Bucket name

    Returns:
        List of objects with metadata

    Raises:
        404: Bucket not found
    """
    if bucket not in buckets:
        raise NotFoundError("Bucket", bucket)

    objects_list = []
    for key, content in buckets[bucket].items():
        metadata = object_metadata[bucket][key]
        objects_list.append({
            "key": key,
            "size": metadata["size"],
            "size_kb": round(metadata["size"] / 1024, 2),
            "etag": metadata["etag"],
            "last_modified": metadata["last_modified"].isoformat(),
            "content_type": metadata["content_type"],
            "storage_class": metadata["storage_class"]
        })

    return {
        "bucket": bucket,
        "object_count": len(objects_list),
        "objects": objects_list
    }


@app.delete("/admin/reset")
async def reset_all_data():
    """Clear all buckets and objects (admin endpoint).

    Useful for test cleanup.

    Returns:
        Confirmation message with deleted counts
    """
    bucket_count = len(buckets)
    object_count = sum(len(objects) for objects in buckets.values())

    buckets.clear()
    object_metadata.clear()

    logger.warning(f"Reset all data: {bucket_count} buckets, {object_count} objects deleted")

    return {
        "message": "All data cleared",
        "buckets_deleted": bucket_count,
        "objects_deleted": object_count
    }


@app.get("/stats")
async def get_statistics():
    """Get current storage statistics.

    Returns:
        Overall storage statistics
    """
    total_objects = sum(len(objects) for objects in buckets.values())
    total_size = sum(
        sum(len(obj) for obj in objects.values())
        for objects in buckets.values()
    )

    return {
        "bucket_count": len(buckets),
        "total_objects": total_objects,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "9000"))
    logger.info(f"Starting S3 Mock Server on port {port}")
    logger.info(f"Presigned URL base: {PRESIGNED_URL_BASE}")
    logger.info("Access docs at: http://localhost:9000/docs")

    uvicorn.run(app, host="0.0.0.0", port=port)
