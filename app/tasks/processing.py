"""Image processing tasks for Celery workers."""

from celery import shared_task
from PIL import Image
import io
import asyncio
import aiosqlite
from typing import Dict, Tuple
from datetime import datetime
from pydantic import BaseModel

from app.db.sqlite import get_db
from app.storage import get_storage
from app.core.config import settings
from app.core.logging_config import get_logger
from app.tasks.celery_app import celery_app


logger = get_logger(__name__)


class VariantMetadata(BaseModel):
    """Metadata for a single image variant.

    Provides type-safe representation of processed image variant properties.
    """
    width: int
    height: int
    aspect_ratio: float
    format: str = "webp"
    size_bytes: int


class ProcessingResult(BaseModel):
    """Complete processing result metadata.

    Encapsulates all metadata generated during image processing,
    including dominant color, original dimensions, and variant details.
    """
    dominant_color: str
    original_dimensions: Dict[str, int]
    variants: Dict[str, VariantMetadata]


def strip_exif_metadata(image: Image.Image) -> Image.Image:
    """Strip ALL metadata including EXIF, GPS, camera info.

    This removes privacy-sensitive data and potential security threats.

    Args:
        image: PIL Image object

    Returns:
        Image: New image without any metadata
    """
    # Extract pixel data
    pixel_data = list(image.getdata())

    # Create new image without metadata
    stripped = Image.new(image.mode, image.size)
    stripped.putdata(pixel_data)

    return stripped


def extract_dominant_color(image: Image.Image) -> str:
    """Extract dominant color for progressive loading placeholders.

    Resizes image to 1x1 pixel to get average color.

    Args:
        image: PIL Image object

    Returns:
        str: Hex color code (e.g., "#3A5F8C")
    """
    # Resize to 1x1 to get average color
    tiny = image.resize((1, 1), Image.Resampling.LANCZOS)
    rgb = tiny.getpixel((0, 0))

    # Handle grayscale images
    if isinstance(rgb, int):
        rgb = (rgb, rgb, rgb)

    # Convert to hex
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def process_variant(
    image: Image.Image,
    max_dimension: int,
    quality: int = 85
) -> Tuple[bytes, VariantMetadata]:
    """Generate single size variant with WebP conversion.

    Maintains aspect ratio while constraining to maximum dimension.

    Args:
        image: PIL Image object
        max_dimension: Maximum width or height
        quality: WebP quality (0-100)

    Returns:
        tuple: (webp_bytes, VariantMetadata)
    """
    width, height = image.size
    aspect_ratio = width / height

    # Calculate new dimensions maintaining aspect ratio
    if width > height:
        new_width = min(max_dimension, width)
        new_height = int(new_width / aspect_ratio)
    else:
        new_height = min(max_dimension, height)
        new_width = int(new_height * aspect_ratio)

    # Only resize if necessary
    if new_width >= width and new_height >= height:
        resized = image
    else:
        resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Convert to WebP
    buffer = io.BytesIO()
    resized.save(buffer, format='WEBP', quality=quality, method=6)
    buffer.seek(0)

    # Generate type-safe metadata using Pydantic model
    metadata = VariantMetadata(
        width=new_width,
        height=new_height,
        aspect_ratio=round(aspect_ratio, 3),
        format='webp',
        size_bytes=buffer.getbuffer().nbytes
    )

    return buffer.read(), metadata


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_image_task(self, job_id: str):
    """Main image processing task.

    Performs:
    1. Load image from staging
    2. Strip EXIF metadata
    3. Extract dominant color
    4. Generate 4 size variants (thumbnail, medium, large, original)
    5. Convert all to WebP
    6. Upload to final storage
    7. Update database status

    Args:
        self: Celery task instance (for retry)
        job_id: Processing job identifier

    Returns:
        dict: Result with job_id, image_id, status

    Raises:
        Exception: Re-raises after max retries
    """
    logger.info("job_processing_started", job_id=job_id)

    db = get_db()
    storage = get_storage()

    try:
        # Update status: processing
        asyncio.run(db.update_job_status(job_id, 'processing'))

        # Get job details
        job = asyncio.run(db.get_job(job_id))

        if not job:
            error_msg = f"Job {job_id} not found in database"
            logger.error("job_not_found", job_id=job_id)
            raise ValueError(error_msg)

        image_id = job['image_id']
        bucket = job['storage_bucket']
        staging_path = job['staging_path']

        logger.info(
            "processing_image",
            job_id=job_id,
            image_id=image_id,
            bucket=bucket,
            staging_path=staging_path,
        )

        # Load raw image from staging
        raw_bytes = asyncio.run(storage.load(bucket, staging_path))
        image = Image.open(io.BytesIO(raw_bytes))

        # Strip EXIF metadata (security + privacy)
        image = strip_exif_metadata(image)
        logger.info("exif_stripped", image_id=image_id, job_id=job_id)

        # Extract dominant color
        dominant_color = extract_dominant_color(image)
        logger.info(
            "dominant_color_extracted",
            image_id=image_id,
            job_id=job_id,
            dominant_color=dominant_color,
        )

        # Process all size variants
        processed_paths = {}
        variants_metadata = {}

        # Convert Pydantic model to dict for iteration
        for variant_name, max_dim in settings.IMAGE_SIZES.model_dump().items():
            logger.debug(
                "variant_generation_started",
                job_id=job_id,
                image_id=image_id,
                variant=variant_name,
                max_dimension=max_dim,
            )

            webp_bytes, meta = process_variant(image, max_dim, settings.WEBP_QUALITY)

            # Storage path
            webp_path = f"processed/{variant_name}/{image_id}_{variant_name}.webp"

            # Upload to final storage
            asyncio.run(storage.save(io.BytesIO(webp_bytes), bucket, webp_path))

            processed_paths[variant_name] = webp_path
            variants_metadata[variant_name] = meta

            logger.info(
                "variant_uploaded",
                job_id=job_id,
                image_id=image_id,
                variant=variant_name,
                size_bytes=meta.size_bytes,
                width=meta.width,
                height=meta.height,
                storage_path=webp_path,
            )

        # Compile complete metadata using type-safe Pydantic model
        processing_result = ProcessingResult(
            dominant_color=dominant_color,
            original_dimensions={
                'width': image.size[0],
                'height': image.size[1]
            },
            variants=variants_metadata
        )

        # Convert to dictionary and merge with existing metadata
        total_metadata = processing_result.model_dump()
        if job.get('processing_metadata'):
            total_metadata = {**job['processing_metadata'], **total_metadata}

        # Update metadata as JSON string
        import json
        job['processing_metadata'] = json.dumps(total_metadata)

        # Update job status: completed
        asyncio.run(db.update_job_status(job_id, 'completed', processed_paths))

        # Cleanup staging file
        try:
            asyncio.run(storage.delete(bucket, staging_path))
            logger.info(
                "staging_cleanup_success",
                job_id=job_id,
                staging_path=staging_path,
            )
        except Exception as e:
            logger.warning(
                "staging_cleanup_failed",
                job_id=job_id,
                staging_path=staging_path,
                error=str(e),
            )

        logger.info(
            "job_completed",
            job_id=job_id,
            image_id=image_id,
            variants_count=len(processed_paths),
            dominant_color=dominant_color,
        )

        return {
            'job_id': job_id,
            'image_id': image_id,
            'status': 'completed'
        }

    except Exception as exc:
        logger.error(
            "job_processing_failed",
            job_id=job_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
            exc_info=True,
        )

        # Check if retry is possible
        can_retry = asyncio.run(db.can_retry(job_id))

        if can_retry:
            asyncio.run(db.update_job_status(job_id, 'retrying', error=str(exc)))
            logger.info(
                "job_retry_scheduled",
                job_id=job_id,
                retry_attempt=self.request.retries + 1,
                max_retries=self.max_retries,
            )
            raise self.retry(exc=exc)
        else:
            asyncio.run(db.update_job_status(job_id, 'failed', error=str(exc)))
            logger.error(
                "job_permanently_failed",
                job_id=job_id,
                retry_attempts=self.request.retries,
                max_retries=self.max_retries,
            )
            raise


@shared_task
def cleanup_old_staging_files():
    """Periodic task to remove old staging files.

    Removes staging files from failed or abandoned jobs older than 24 hours.

    Returns:
        int: Number of files cleaned
    """
    from datetime import timedelta

    db = get_db()
    storage = get_storage()

    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()

    async def do_cleanup():
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute("""
                SELECT job_id, storage_bucket, staging_path
                FROM processing_jobs
                WHERE status IN ('failed', 'pending')
                AND created_at < ?
                AND staging_path IS NOT NULL
            """, (cutoff,)) as cursor:
                rows = await cursor.fetchall()

        cleaned = 0
        for row in rows:
            try:
                await storage.delete(row[1], row[2])
                cleaned += 1
            except Exception as e:
                logger.warning(
                    "staging_file_cleanup_failed",
                    staging_path=row[2],
                    error=str(e),
                )

        return cleaned

    cleaned = asyncio.run(do_cleanup())
    logger.info("staging_cleanup_completed", files_cleaned=cleaned)
    return cleaned


@shared_task
def cleanup_old_rate_limits():
    """Periodic task to remove old rate limit windows.

    Removes rate limit entries older than 24 hours to prevent database bloat.

    Returns:
        int: Number of records deleted
    """
    from datetime import timedelta

    db = get_db()
    cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()

    async def do_cleanup():
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "DELETE FROM upload_rate_limits WHERE window_start < ?",
                (cutoff,)
            )
            await conn.commit()
            return conn.total_changes

    deleted = asyncio.run(do_cleanup())
    logger.info("rate_limits_cleanup_completed", records_deleted=deleted)
    return deleted


# Register periodic tasks
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic cleanup tasks.

    Runs every hour to maintain system hygiene.
    """
    # Cleanup staging files every hour
    sender.add_periodic_task(
        3600.0,
        cleanup_old_staging_files.s(),
        name='cleanup-staging-hourly'
    )

    # Cleanup rate limits every hour
    sender.add_periodic_task(
        3600.0,
        cleanup_old_rate_limits.s(),
        name='cleanup-rate-limits-hourly'
    )

# Updated: 2025-11-18 22:01 UTC - Production-ready code
