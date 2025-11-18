"""
Upload API endpoints for image processing.

Clean Architecture Pattern:
- Router handles HTTP concerns (headers, status codes, request/response format)
- Service Layer handles business logic (orchestration, validation, persistence)
- Dependencies inject required services and validate auth/rate limits
"""

from fastapi import APIRouter, UploadFile, File, Form, Depends, status
from fastapi.responses import JSONResponse
from typing import Optional

from app.api.dependencies import (
    verify_content_length,
    validate_image_file,
    require_bucket_access,
    check_rate_limit,
    get_image_service,
    AuthContext
)
from app.services.image_service import ImageService
from app.db.sqlite import get_db
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
    rate_limit: dict = Depends(check_rate_limit),
    service: ImageService = Depends(get_image_service)
):
    """Upload image for asynchronous processing.

    **Clean Architecture Pattern:**
    1. Router validates HTTP-level concerns (file size, MIME type)
    2. Dependencies enforce auth and rate limits
    3. Service layer orchestrates business logic
    4. Router constructs HTTP response

    **Authorization**: Requires bucket-specific access via distributed authorization system.
    - Group buckets (org-{org_id}/groups/{group_id}/): Requires group membership
    - User buckets (org-{org_id}/users/{user_id}/): Owner only
    - System buckets (org-{org_id}/system/): All authenticated users

    Args:
        file: Image file upload (JPEG, PNG, WebP)
        bucket: Target storage bucket (must match format: org-{org_id}/groups/{group_id}/)
        metadata: Optional JSON metadata (pass-through)
        content_length: Pre-validated content length (via dependency)
        auth: Authenticated user context with bucket access (via dependency)
        rate_limit: Rate limit check result (via dependency)
        service: Image processing service (via dependency injection)

    Returns:
        JSONResponse: 202 Accepted with job_id, image_id, status_url

    Raises:
        HTTPException: 400 if invalid bucket format
        HTTPException: 413 if file too large
        HTTPException: 415 if file type unsupported
        HTTPException: 429 if rate limit exceeded
        HTTPException: 403 if permission denied or org mismatch
        HTTPException: 503 if authorization service unavailable
        ServiceError: On business logic failures (converted to HTTP errors)
    """
    logger.info(
        "upload_request_received",
        filename=file.filename,
        bucket=bucket,
        content_type=file.content_type,
        content_length=content_length,
        user_id=auth.user_id,
        org_id=auth.org_id,
    )

    # 1. HTTP-Level Validation: MIME Type Check
    # This stays in router because it's about HTTP request parsing
    detected_mime = await validate_image_file(file)
    logger.debug(
        "image_validation_success",
        filename=file.filename,
        detected_mime=detected_mime,
        declared_content_type=file.content_type,
    )

    # 2. Delegate to Service Layer (Business Logic)
    result = await service.process_new_upload(
        file=file,
        bucket=bucket,
        auth_user_id=auth.user_id,
        auth_org_id=auth.org_id,
        metadata_json=metadata,
        content_length=content_length,
        detected_mime=detected_mime
    )

    # 3. Construct HTTP Response
    logger.info(
        "upload_accepted",
        job_id=result["job_id"],
        image_id=result["image_id"],
        user_id=auth.user_id,
        org_id=auth.org_id,
        filename=file.filename,
        rate_limit_remaining=rate_limit["remaining"],
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": result["job_id"],
            "image_id": result["image_id"],
            "status_url": result["status_url"],
            "message": "Upload accepted. Processing initiated."
        },
        headers={
            "X-RateLimit-Limit": str(settings.RATE_LIMIT_MAX_UPLOADS),
            "X-RateLimit-Remaining": str(rate_limit["remaining"]),
            "X-RateLimit-Reset": rate_limit["reset_at"]
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
