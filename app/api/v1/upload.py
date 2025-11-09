"""Upload API endpoints for image processing."""

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import JSONResponse
from uuid import uuid4
from typing import Optional
from datetime import datetime
import json

from app.api.dependencies import (
    verify_content_length,
    check_rate_limit,
    validate_image_file
)
from app.storage import get_storage
from app.db.sqlite import get_db
from app.tasks.celery_app import process_image_task
from app.core.config import settings


router = APIRouter(prefix="/api/v1/images", tags=["upload"])


@router.post("/upload", status_code=202)
async def upload_image(
    file: UploadFile = File(...),
    bucket: str = Form(...),
    metadata: Optional[str] = Form("{}"),
    content_length: int = Depends(verify_content_length),
    rate_limit: dict = Depends(check_rate_limit),
    storage=Depends(get_storage),
    db=Depends(get_db)
):
    """Upload image for asynchronous processing.

    Returns job_id for status polling and image_id as permanent identifier.
    Processing happens in background via Celery workers.

    Args:
        file: Image file upload (JPEG, PNG, WebP)
        bucket: Target storage bucket name
        metadata: Optional JSON metadata (pass-through)
        content_length: Pre-validated content length
        rate_limit: Rate limit check result
        storage: Storage backend instance
        db: Database instance

    Returns:
        JSONResponse: 202 Accepted with job_id, image_id, status_url

    Raises:
        HTTPException: 415 if file type unsupported
        HTTPException: 413 if file too large
        HTTPException: 429 if rate limit exceeded
    """
    # Validate image type via magic bytes
    detected_mime = await validate_image_file(file)

    # Parse metadata JSON
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        meta = {}

    # Generate unique identifiers
    job_id = str(uuid4())
    image_id = str(uuid4())
    staging_path = f"staging/{image_id}_{int(datetime.utcnow().timestamp())}"

    # Augment metadata with processing info
    processing_metadata = {
        **meta,
        "uploader_id": rate_limit["user_id"],
        "original_filename": file.filename,
        "detected_mime_type": detected_mime,
        "content_length": content_length,
    }

    # Create job in database
    await db.create_job(
        job_id=job_id,
        image_id=image_id,
        storage_bucket=bucket,
        staging_path=staging_path,
        metadata=processing_metadata
    )

    # Save to staging area
    await storage.save(file.file, bucket, staging_path)

    # Queue processing task (async via Celery)
    process_image_task.delay(job_id)

    # Return 202 Accepted
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
    job = await db.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

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
    job = await db.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Processing not completed. Current status: {job['status']}"
        )

    return {
        "job_id": job["job_id"],
        "image_id": job["image_id"],
        "status": "completed",
        "urls": job["processed_paths"],
        "metadata": job["processing_metadata"],
        "completed_at": job["completed_at"]
    }
