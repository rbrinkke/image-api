"""Retrieval API endpoints for accessing processed images."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from typing import Literal, Optional
from enum import Enum

from app.db.sqlite import get_db
from app.storage import get_storage
from app.core.logging_config import get_logger
from app.api.dependencies import require_permission, require_bucket_read_access, AuthContext


logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/images", tags=["retrieval"])


class ImageSize(str, Enum):
    """Available image size variants."""
    thumbnail = "thumbnail"
    medium = "medium"
    large = "large"
    original = "original"


@router.get("/{image_id}")
async def get_image_info(
    request: Request,
    image_id: str,
    size: ImageSize = Query(ImageSize.medium),
    db=Depends(get_db),
    storage=Depends(get_storage)
):
    """Get image URL and metadata by image_id.

    **Authorization**:
    - System buckets: Public access (no auth required)
    - User buckets: Owner only
    - Group buckets: Group members only

    Args:
        request: HTTP request for auth context
        image_id: Image identifier
        size: Desired size variant
        db: Database instance
        storage: Storage backend

    Returns:
        dict: Image URL and metadata

    Raises:
        HTTPException: 404 if image not found or size not available
        HTTPException: 401 if auth required but not provided
        HTTPException: 403 if access denied
    """
    logger.debug(
        "image_info_request",
        image_id=image_id,
        size=size.value,
    )

    job = await db.get_job_by_image_id(image_id)

    if not job:
        logger.warning("image_not_found", image_id=image_id)
        raise HTTPException(status_code=404, detail="Image not found")

    # Check bucket access authorization
    bucket = job["storage_bucket"]
    auth = await require_bucket_read_access(request, bucket)

    logger.debug(
        "bucket_read_access_granted",
        image_id=image_id,
        bucket=bucket,
        authenticated=auth is not None,
    )

    paths = job["processed_paths"]
    if size.value not in paths:
        logger.warning(
            "image_size_not_available",
            image_id=image_id,
            requested_size=size.value,
            available_sizes=list(paths.keys()) if paths else [],
        )
        raise HTTPException(status_code=404, detail=f"Size '{size.value}' not available")

    path = paths[size.value]
    url = await storage.get_url(bucket, path)

    metadata = job["processing_metadata"]

    logger.info(
        "image_info_returned",
        image_id=image_id,
        size=size.value,
        bucket=bucket,
    )

    return {
        "image_id": image_id,
        "url": url,
        "size": size.value,
        "metadata": {
            "dominant_color": metadata.get("dominant_color"),
            "dimensions": metadata.get("variants", {}).get(size.value, {})
        }
    }


@router.get("/{image_id}/all")
async def get_all_image_sizes(
    request: Request,
    image_id: str,
    db=Depends(get_db),
    storage=Depends(get_storage)
):
    """Get all size variants for an image.

    **Authorization**:
    - System buckets: Public access (no auth required)
    - User buckets: Owner only
    - Group buckets: Group members only

    Args:
        request: HTTP request for auth context
        image_id: Image identifier
        db: Database instance
        storage: Storage backend

    Returns:
        dict: All variant URLs and complete metadata

    Raises:
        HTTPException: 404 if image not found
        HTTPException: 401 if auth required but not provided
        HTTPException: 403 if access denied
    """
    logger.debug("all_sizes_request", image_id=image_id)

    job = await db.get_job_by_image_id(image_id)

    if not job:
        logger.warning("all_sizes_not_found", image_id=image_id)
        raise HTTPException(status_code=404, detail="Image not found")

    # Check bucket access authorization
    bucket = job["storage_bucket"]
    auth = await require_bucket_read_access(request, bucket)

    logger.debug(
        "bucket_read_access_granted_all",
        image_id=image_id,
        bucket=bucket,
        authenticated=auth is not None,
    )

    paths = job["processed_paths"]

    # Generate URLs for all variants asynchronously
    urls = {}
    for variant, path in paths.items():
        urls[variant] = await storage.get_url(bucket, path)

    logger.info(
        "all_sizes_returned",
        image_id=image_id,
        variants_count=len(urls),
        bucket=bucket,
    )

    return {
        "image_id": image_id,
        "urls": urls,
        "metadata": job["processing_metadata"]
    }


@router.get("/{image_id}/direct")
async def serve_image_direct(
    request: Request,
    image_id: str,
    size: ImageSize = Query(ImageSize.medium),
    db=Depends(get_db),
    storage=Depends(get_storage)
):
    """Direct image file serving or redirect to presigned URL.

    For local storage: serves file directly with caching headers.
    For S3 storage: redirects to presigned URL.

    **Authorization**:
    - System buckets: Public access (no auth required)
    - User buckets: Owner only
    - Group buckets: Group members only

    Args:
        request: HTTP request for auth context
        image_id: Image identifier
        size: Desired size variant
        db: Database instance
        storage: Storage backend

    Returns:
        FileResponse or RedirectResponse

    Raises:
        HTTPException: 404 if image or size not found
        HTTPException: 401 if auth required but not provided
        HTTPException: 403 if access denied
    """
    logger.debug(
        "direct_image_request",
        image_id=image_id,
        size=size.value,
    )

    job = await db.get_job_by_image_id(image_id)

    if not job:
        logger.warning(
            "direct_image_not_found",
            image_id=image_id,
            size=size.value,
        )
        raise HTTPException(status_code=404, detail="Image not found")

    # Check bucket access authorization
    bucket = job["storage_bucket"]
    auth = await require_bucket_read_access(request, bucket)

    logger.debug(
        "bucket_read_access_granted_direct",
        image_id=image_id,
        bucket=bucket,
        authenticated=auth is not None,
    )

    paths = job["processed_paths"]
    if size.value not in paths:
        logger.warning(
            "direct_image_size_not_available",
            image_id=image_id,
            size=size.value,
            available_sizes=list(paths.keys()),
        )
        raise HTTPException(status_code=404, detail=f"Size '{size.value}' not available")

    path = paths[size.value]

    # Local storage: serve file directly
    if hasattr(storage, 'get_local_path'):
        local_path = storage.get_local_path(bucket, path)
        logger.info(
            "direct_image_served_local",
            image_id=image_id,
            size=size.value,
            local_path=str(local_path),
            cache_control="public, max-age=31536000, immutable",
        )
        return FileResponse(
            local_path,
            media_type="image/webp",
            headers={
                "Cache-Control": "public, max-age=31536000, immutable"
            }
        )
    # S3 storage: redirect to presigned URL
    else:
        url = await storage.get_url(bucket, path, expires_in=3600)
        logger.info(
            "direct_image_redirected_s3",
            image_id=image_id,
            size=size.value,
            expires_in=3600,
        )
        return RedirectResponse(url=url, status_code=307)


@router.delete("/{image_id}")
async def delete_image(
    request: Request,
    image_id: str,
    db=Depends(get_db),
    storage=Depends(get_storage)
):
    """Delete image and all its variants.

    Removes all processed files from storage.
    Database records are retained for audit trail.

    **Authorization**: Requires bucket-specific delete access.
    - Group buckets: Requires group membership
    - User buckets: Owner only
    - System buckets: All authenticated users

    Args:
        request: HTTP request for auth context
        image_id: Image identifier
        db: Database instance
        storage: Storage backend

    Returns:
        dict: Deletion confirmation with file count

    Raises:
        HTTPException: 404 if image not found
        HTTPException: 401 if not authenticated
        HTTPException: 403 if permission denied
        HTTPException: 503 if authorization service unavailable
    """
    # Get job first to determine bucket
    job = await db.get_job_by_image_id(image_id)

    if not job:
        logger.warning("image_deletion_not_found", image_id=image_id)
        raise HTTPException(status_code=404, detail="Image not found")

    # Check bucket access authorization for delete operation
    bucket = job["storage_bucket"]
    auth = await require_bucket_read_access(request, bucket)

    # Delete requires authentication (no public deletes)
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for deletion"
        )

    logger.info(
        "image_deletion_request",
        image_id=image_id,
        user_id=auth.user_id,
        org_id=auth.org_id,
        bucket=bucket,
    )

    deleted_count = 0
    failed_deletions = []

    # Delete all processed variants
    if job["processed_paths"]:
        for variant, path in job["processed_paths"].items():
            try:
                await storage.delete(bucket, path)
                deleted_count += 1
                logger.debug(
                    "variant_deleted",
                    image_id=image_id,
                    variant=variant,
                    path=path,
                )
            except Exception as exc:
                logger.warning(
                    "variant_deletion_failed",
                    image_id=image_id,
                    variant=variant,
                    path=path,
                    error=str(exc),
                )
                failed_deletions.append(f"{variant}:{path}")

    # Delete staging file if exists
    if job["staging_path"]:
        try:
            await storage.delete(bucket, job["staging_path"])
            deleted_count += 1
            logger.debug(
                "staging_file_deleted",
                image_id=image_id,
                staging_path=job["staging_path"],
            )
        except Exception as exc:
            logger.warning(
                "staging_deletion_failed",
                image_id=image_id,
                staging_path=job["staging_path"],
                error=str(exc),
            )
            failed_deletions.append(f"staging:{job['staging_path']}")

    # Note: Database records kept for audit trail
    # In production, consider adding 'deleted' flag instead

    logger.info(
        "image_deletion_completed",
        image_id=image_id,
        user_id=auth.user_id,
        org_id=auth.org_id,
        files_removed=deleted_count,
        failed_deletions=len(failed_deletions),
        failed_files=failed_deletions if failed_deletions else None,
    )

    return {
        "image_id": image_id,
        "deleted": True,
        "files_removed": deleted_count
    }


@router.get("/batch")
async def get_images_batch(
    request: Request,
    image_ids: str = Query(..., description="Comma-separated image UUIDs"),
    size: ImageSize = Query(ImageSize.medium),
    db=Depends(get_db),
    storage=Depends(get_storage)
):
    """Batch retrieval for multiple images.

    Maximum 50 images per request for performance.

    **Authorization**: Each image checked individually based on bucket access.
    - System buckets: Public access
    - User buckets: Owner only
    - Group buckets: Group members only

    Args:
        request: HTTP request for auth context
        image_ids: Comma-separated list of image IDs
        size: Desired size variant for all images
        db: Database instance
        storage: Storage backend

    Returns:
        dict: List of image results with requested/found counts
        Note: Images with denied access are silently omitted from results

    Raises:
        HTTPException: 400 if more than 50 images requested
    """
    ids = [id.strip() for id in image_ids.split(',')]

    logger.info(
        "batch_retrieval_request",
        image_count=len(ids),
        size=size.value,
    )

    if len(ids) > 50:
        logger.warning(
            "batch_retrieval_limit_exceeded",
            requested_count=len(ids),
            max_allowed=50,
        )
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 images per request. Please split into multiple requests."
        )

    results = []
    failed_ids = []

    for image_id in ids:
        try:
            job = await db.get_job_by_image_id(image_id)
            if job and job["processed_paths"].get(size.value):
                bucket = job["storage_bucket"]

                # Check bucket access for this image
                try:
                    auth = await require_bucket_read_access(request, bucket)
                except HTTPException as auth_exc:
                    # Access denied - silently skip this image
                    logger.debug(
                        "batch_item_access_denied",
                        image_id=image_id,
                        bucket=bucket,
                        error=auth_exc.detail
                    )
                    failed_ids.append(image_id)
                    continue

                path = job["processed_paths"][size.value]
                url = await storage.get_url(bucket, path)

                results.append({
                    "image_id": image_id,
                    "url": url,
                    "size": size.value,
                    "dominant_color": job["processing_metadata"].get("dominant_color")
                })
            else:
                failed_ids.append(image_id)
        except Exception as exc:
            logger.debug(
                "batch_retrieval_item_failed",
                image_id=image_id,
                error=str(exc),
            )
            failed_ids.append(image_id)

    logger.info(
        "batch_retrieval_completed",
        requested_count=len(ids),
        found_count=len(results),
        failed_count=len(failed_ids),
        success_rate=round(len(results) / len(ids) * 100, 2) if ids else 0,
    )

    return {
        "images": results,
        "requested": len(ids),
        "found": len(results)
    }
