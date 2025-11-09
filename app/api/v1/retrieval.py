"""Retrieval API endpoints for accessing processed images."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from typing import Literal
from enum import Enum

from app.db.sqlite import get_db
from app.storage import get_storage


router = APIRouter(prefix="/api/v1/images", tags=["retrieval"])


class ImageSize(str, Enum):
    """Available image size variants."""
    thumbnail = "thumbnail"
    medium = "medium"
    large = "large"
    original = "original"


@router.get("/{image_id}")
async def get_image_info(
    image_id: str,
    size: ImageSize = Query(ImageSize.medium),
    db=Depends(get_db),
    storage=Depends(get_storage)
):
    """Get image URL and metadata by image_id.

    Args:
        image_id: Image identifier
        size: Desired size variant
        db: Database instance
        storage: Storage backend

    Returns:
        dict: Image URL and metadata

    Raises:
        HTTPException: 404 if image not found or size not available
    """
    job = await db.get_job_by_image_id(image_id)

    if not job:
        raise HTTPException(status_code=404, detail="Image not found")

    paths = job["processed_paths"]
    if size.value not in paths:
        raise HTTPException(status_code=404, detail=f"Size '{size.value}' not available")

    bucket = job["storage_bucket"]
    path = paths[size.value]
    url = storage.get_url(bucket, path)

    metadata = job["processing_metadata"]

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
    image_id: str,
    db=Depends(get_db),
    storage=Depends(get_storage)
):
    """Get all size variants for an image.

    Args:
        image_id: Image identifier
        db: Database instance
        storage: Storage backend

    Returns:
        dict: All variant URLs and complete metadata

    Raises:
        HTTPException: 404 if image not found
    """
    job = await db.get_job_by_image_id(image_id)

    if not job:
        raise HTTPException(status_code=404, detail="Image not found")

    bucket = job["storage_bucket"]
    paths = job["processed_paths"]

    urls = {
        variant: storage.get_url(bucket, path)
        for variant, path in paths.items()
    }

    return {
        "image_id": image_id,
        "urls": urls,
        "metadata": job["processing_metadata"]
    }


@router.get("/{image_id}/direct")
async def serve_image_direct(
    image_id: str,
    size: ImageSize = Query(ImageSize.medium),
    db=Depends(get_db),
    storage=Depends(get_storage)
):
    """Direct image file serving or redirect to presigned URL.

    For local storage: serves file directly with caching headers.
    For S3 storage: redirects to presigned URL.

    Args:
        image_id: Image identifier
        size: Desired size variant
        db: Database instance
        storage: Storage backend

    Returns:
        FileResponse or RedirectResponse

    Raises:
        HTTPException: 404 if image or size not found
    """
    job = await db.get_job_by_image_id(image_id)

    if not job:
        raise HTTPException(status_code=404, detail="Image not found")

    paths = job["processed_paths"]
    if size.value not in paths:
        raise HTTPException(status_code=404, detail=f"Size '{size.value}' not available")

    bucket = job["storage_bucket"]
    path = paths[size.value]

    # Local storage: serve file directly
    if hasattr(storage, 'get_local_path'):
        local_path = storage.get_local_path(bucket, path)
        return FileResponse(
            local_path,
            media_type="image/webp",
            headers={
                "Cache-Control": "public, max-age=31536000, immutable"
            }
        )
    # S3 storage: redirect to presigned URL
    else:
        url = storage.get_url(bucket, path, expires_in=3600)
        return RedirectResponse(url=url, status_code=307)


@router.delete("/{image_id}")
async def delete_image(
    image_id: str,
    db=Depends(get_db),
    storage=Depends(get_storage)
):
    """Delete image and all its variants.

    Removes all processed files from storage.
    Database records are retained for audit trail.

    Args:
        image_id: Image identifier
        db: Database instance
        storage: Storage backend

    Returns:
        dict: Deletion confirmation with file count

    Raises:
        HTTPException: 404 if image not found
    """
    job = await db.get_job_by_image_id(image_id)

    if not job:
        raise HTTPException(status_code=404, detail="Image not found")

    bucket = job["storage_bucket"]
    deleted_count = 0

    # Delete all processed variants
    if job["processed_paths"]:
        for variant, path in job["processed_paths"].items():
            try:
                await storage.delete(bucket, path)
                deleted_count += 1
            except Exception:
                pass  # Continue even if some fail

    # Delete staging file if exists
    if job["staging_path"]:
        try:
            await storage.delete(bucket, job["staging_path"])
            deleted_count += 1
        except Exception:
            pass

    # Note: Database records kept for audit trail
    # In production, consider adding 'deleted' flag instead

    return {
        "image_id": image_id,
        "deleted": True,
        "files_removed": deleted_count
    }


@router.get("/batch")
async def get_images_batch(
    image_ids: str = Query(..., description="Comma-separated image UUIDs"),
    size: ImageSize = Query(ImageSize.medium),
    db=Depends(get_db),
    storage=Depends(get_storage)
):
    """Batch retrieval for multiple images.

    Maximum 50 images per request for performance.

    Args:
        image_ids: Comma-separated list of image IDs
        size: Desired size variant for all images
        db: Database instance
        storage: Storage backend

    Returns:
        dict: List of image results with requested/found counts

    Raises:
        HTTPException: 400 if more than 50 images requested
    """
    ids = [id.strip() for id in image_ids.split(',')]

    if len(ids) > 50:
        raise HTTPException(
            status_code=400,
            detail="Maximum 50 images per request. Please split into multiple requests."
        )

    results = []
    for image_id in ids:
        try:
            job = await db.get_job_by_image_id(image_id)
            if job and job["processed_paths"].get(size.value):
                bucket = job["storage_bucket"]
                path = job["processed_paths"][size.value]
                url = storage.get_url(bucket, path)

                results.append({
                    "image_id": image_id,
                    "url": url,
                    "size": size.value,
                    "dominant_color": job["processing_metadata"].get("dominant_color")
                })
        except Exception:
            # Skip failed retrievals
            continue

    return {
        "images": results,
        "requested": len(ids),
        "found": len(results)
    }
