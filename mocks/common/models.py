"""Shared Pydantic models for mock servers."""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class HealthStatus(str, Enum):
    """Health check status values."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthResponse(BaseModel):
    """Standard health check response."""
    status: HealthStatus = Field(..., description="Service health status")
    service: str = Field(..., description="Service name")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Current timestamp")
    version: str = Field(default="1.0.0", description="Service version")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional health details")


class ErrorResponse(BaseModel):
    """Standard error response format."""
    error: str = Field(..., description="Error type or code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error context")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Invalid file format",
                "details": {"allowed_formats": ["jpg", "png", "webp"]},
                "timestamp": "2025-11-09T12:00:00Z"
            }
        }


class JobStatus(str, Enum):
    """Processing job status values."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImageSize(str, Enum):
    """Image variant sizes."""
    THUMBNAIL = "thumbnail"
    MEDIUM = "medium"
    LARGE = "large"
    ORIGINAL = "original"


class ImageMetadata(BaseModel):
    """Image metadata structure."""
    uploader_id: str = Field(..., description="User who uploaded the image")
    original_filename: str = Field(..., description="Original file name")
    detected_mime_type: str = Field(..., description="Detected MIME type via magic bytes")
    content_length: int = Field(..., description="File size in bytes")
    context: Optional[str] = Field(None, description="Application context")

    @validator('content_length')
    def validate_content_length(cls, v):
        if v < 0:
            raise ValueError('content_length must be non-negative')
        return v


class ProcessingResult(BaseModel):
    """Result of image processing job."""
    job_id: str = Field(..., description="Unique job identifier")
    image_id: str = Field(..., description="Permanent image identifier")
    status: JobStatus = Field(..., description="Current job status")
    urls: Optional[Dict[str, str]] = Field(None, description="URLs for each image variant")
    metadata: Optional[ImageMetadata] = Field(None, description="Image metadata")
    dominant_color: Optional[str] = Field(None, description="Dominant color hex code")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    error: Optional[str] = Field(None, description="Error message if failed")


class UploadRequest(BaseModel):
    """Image upload request metadata."""
    bucket: str = Field(..., description="Storage bucket name", min_length=1, max_length=100)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata")

    @validator('bucket')
    def validate_bucket(cls, v):
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('bucket name must contain only alphanumeric characters, hyphens, and underscores')
        return v


class WebhookEvent(BaseModel):
    """Webhook notification event."""
    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Event type (e.g., 'image.processed')")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    data: Dict[str, Any] = Field(..., description="Event payload data")
    signature: Optional[str] = Field(None, description="HMAC signature for verification")


class S3Object(BaseModel):
    """S3 object metadata."""
    key: str = Field(..., description="Object key (path)")
    size: int = Field(..., description="Object size in bytes")
    last_modified: datetime = Field(default_factory=datetime.utcnow, description="Last modification time")
    etag: str = Field(..., description="Entity tag (MD5 hash)")
    storage_class: str = Field(default="STANDARD", description="S3 storage class")


class PresignedUrlResponse(BaseModel):
    """Presigned URL generation response."""
    url: str = Field(..., description="Presigned URL for object access")
    expires_at: datetime = Field(..., description="URL expiration timestamp")
    expires_in: int = Field(..., description="Seconds until expiration")
