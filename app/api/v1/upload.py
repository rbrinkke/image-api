"""Upload API endpoints for image processing."""

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from uuid import uuid4
from typing import Optional
from datetime import datetime
import json

from app.api.dependencies import (
    verify_content_length,
    validate_image_file,
    require_permission,
    require_bucket_access,
    AuthContext
)
from app.storage import get_storage
from app.db.sqlite import get_db
from app.tasks.celery_app import process_image_task
from app.core.config import settings
from app.core.logging_config import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/images", tags=["upload"])


@router.post("/upload", status_code=202)
async def upload_image(
    file: UploadFile = File(...),
    bucket: str = Form(...),
    metadata: Optional[str] = Form("{}"),
    content_length: int = Depends(verify_content_length),
    auth: AuthContext = Depends(require_bucket_access("image:upload")),
    storage=Depends(get_storage),
    db=Depends(get_db)
):
    """Upload image for asynchronous processing.

    Returns job_id for status polling and image_id as permanent identifier.
    Processing happens in background via Celery workers.

    **Authorization**: Requires bucket-specific access via distributed authorization system.
    - Group buckets (org-{org_id}/groups/{group_id}/): Requires group membership
    - User buckets (org-{org_id}/users/{user_id}/): Owner only
    - System buckets (org-{org_id}/system/): All authenticated users

    Args:
        file: Image file upload (JPEG, PNG, WebP)
        bucket: Target storage bucket (must match format: org-{org_id}/groups/{group_id}/)
        metadata: Optional JSON metadata (pass-through)
        content_length: Pre-validated content length
        auth: Authenticated user context (with bucket access check)
        storage: Storage backend instance
        db: Database instance

    Returns:
        JSONResponse: 202 Accepted with job_id, image_id, status_url

    Raises:
        HTTPException: 400 if invalid bucket format
        HTTPException: 413 if file too large
        HTTPException: 415 if file type unsupported
        HTTPException: 429 if rate limit exceeded
        HTTPException: 403 if permission denied or org mismatch
        HTTPException: 503 if authorization service unavailable
    """
    # Check rate limit (after permission check)
    rate_limit_result = await db.check_rate_limit(auth.user_id, settings.RATE_LIMIT_MAX_UPLOADS)

    if not rate_limit_result["allowed"]:
        logger.warning(
            "upload_rate_limit_exceeded",
            user_id=auth.user_id,
            org_id=auth.org_id,
            filename=file.filename,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {settings.RATE_LIMIT_MAX_UPLOADS} uploads per hour.",
            headers={
                "X-RateLimit-Limit": str(settings.RATE_LIMIT_MAX_UPLOADS),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": rate_limit_result["reset_at"],
                "Retry-After": "3600"
            }
        )

    logger.info(
        "upload_request_received",
        filename=file.filename,
        bucket=bucket,
        content_type=file.content_type,
        content_length=content_length,
        user_id=auth.user_id,
        org_id=auth.org_id,
    )

    # Validate image type via magic bytes
    try:
        detected_mime = await validate_image_file(file)
        logger.debug(
            "image_validation_success",
            filename=file.filename,
            detected_mime=detected_mime,
            declared_content_type=file.content_type,
        )
    except HTTPException as exc:
        logger.warning(
            "image_validation_failed",
            filename=file.filename,
            content_type=file.content_type,
            error=exc.detail,
            status_code=exc.status_code,
        )
        raise

    # Parse metadata JSON
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError as e:
        logger.warning(
            "metadata_json_parse_failed",
            metadata=metadata,
            error=str(e),
        )
        meta = {}

    # Generate unique identifiers
    job_id = str(uuid4())
    image_id = str(uuid4())
    staging_path = f"staging/{image_id}_{int(datetime.utcnow().timestamp())}"

    logger.debug(
        "upload_identifiers_generated",
        job_id=job_id,
        image_id=image_id,
        staging_path=staging_path,
    )

    # Augment metadata with processing info
    processing_metadata = {
        **meta,
        "uploader_id": auth.user_id,
        "org_id": auth.org_id,
        "original_filename": file.filename,
        "detected_mime_type": detected_mime,
        "content_length": content_length,
    }

    # Create job in database
    try:
        await db.create_job(
            job_id=job_id,
            image_id=image_id,
            storage_bucket=bucket,
            staging_path=staging_path,
            metadata=processing_metadata
        )
        logger.debug(
            "job_created_in_database",
            job_id=job_id,
            image_id=image_id,
        )
    except Exception as exc:
        logger.error(
            "job_creation_failed",
            job_id=job_id,
            image_id=image_id,
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to create processing job")

    # Save to staging area
    try:
        await storage.save(file.file, bucket, staging_path)
        logger.info(
            "file_saved_to_staging",
            job_id=job_id,
            image_id=image_id,
            bucket=bucket,
            staging_path=staging_path,
        )
    except Exception as exc:
        logger.error(
            "staging_save_failed",
            job_id=job_id,
            image_id=image_id,
            bucket=bucket,
            staging_path=staging_path,
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to save file to staging")

    # Queue processing task (async via Celery)
    try:
        process_image_task.delay(job_id)
        logger.info(
            "processing_task_queued",
            job_id=job_id,
            image_id=image_id,
        )
    except Exception as exc:
        logger.error(
            "task_queue_failed",
            job_id=job_id,
            image_id=image_id,
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to queue processing task")

    # Return 202 Accepted
    logger.info(
        "upload_accepted",
        job_id=job_id,
        image_id=image_id,
        user_id=auth.user_id,
        org_id=auth.org_id,
        filename=file.filename,
        rate_limit_remaining=rate_limit_result["remaining"],
    )

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "image_id": image_id,
            "status_url": f"/api/v1/images/jobs/{job_id}",
            "message": "Upload accepted. Processing initiated."
        },
        headers={
            "X-RateLimit-Limit": str(settings.RATE_LIMIT_MAX_UPLOADS),
            "X-RateLimit-Remaining": str(rate_limit_result["remaining"]),
            "X-RateLimit-Reset": rate_limit_result["reset_at"]
        }
    )


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, db=Depends(get_db)):
    """Get processing job status.

    Poll this endpoint to check if processing is complete.

    Args:
        job_id: Job identifier from upload response
        db: Database instance

    Returns:
        dict: Job status with job_id, image_id, status, timestamps

    Raises:
        HTTPException: 404 if job not found
    """
    logger.debug("job_status_query", job_id=job_id)

    job = await db.get_job(job_id)

    if not job:
        logger.warning("job_status_not_found", job_id=job_id)
        raise HTTPException(status_code=404, detail="Job not found")

    logger.info(
        "job_status_returned",
        job_id=job_id,
        image_id=job["image_id"],
        status=job["status"],
    )

    return {
        "job_id": job["job_id"],
        "image_id": job["image_id"],
        "status": job["status"],
        "created_at": job["created_at"],
        "completed_at": job.get("completed_at"),
        "error": job.get("last_error"),
        "attempts": job["attempt_count"]
    }


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str, db=Depends(get_db)):
    """Get processed image results.

    Only returns successfully if job status is 'completed'.
    Returns all variant URLs and metadata.

    Args:
        job_id: Job identifier
        db: Database instance

    Returns:
        dict: Complete result with URLs, metadata, dominant color

    Raises:
        HTTPException: 404 if job not found
        HTTPException: 409 if processing not completed
    """
    logger.debug("job_result_query", job_id=job_id)

    job = await db.get_job(job_id)

    if not job:
        logger.warning("job_result_not_found", job_id=job_id)
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        logger.warning(
            "job_result_not_ready",
            job_id=job_id,
            current_status=job["status"],
        )
        raise HTTPException(
            status_code=409,
            detail=f"Processing not completed. Current status: {job['status']}"
        )

    logger.info(
        "job_result_returned",
        job_id=job_id,
        image_id=job["image_id"],
        variants_count=len(job["processed_paths"]) if job["processed_paths"] else 0,
    )

    return {
        "job_id": job["job_id"],
        "image_id": job["image_id"],
        "status": "completed",
        "urls": job["processed_paths"],
        "metadata": job["processing_metadata"],
        "completed_at": job["completed_at"]
    }
