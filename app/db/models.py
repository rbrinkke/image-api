"""SQLAlchemy models for the application."""

from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import String, Integer, JSON, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ProcessingJob(Base):
    """Model for processing jobs."""
    __tablename__ = "processing_jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    image_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)  # pending, processing, completed, failed, retrying

    # Storage information
    storage_bucket: Mapped[str] = mapped_column(String, nullable=False)
    staging_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    processed_paths: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    processing_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Ownership information (for RBAC)
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    organization_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # Retry mechanism
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    # Using DateTime with timezone=True is best practice for Postgres,
    # but SQLite doesn't support it natively. SQLAlchemy handles the conversion.
    # For SQLite, use CURRENT_TIMESTAMP instead of func.now()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ImageUploadEvent(Base):
    """Model for image upload events (audit trail)."""
    __tablename__ = "image_upload_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    image_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    job_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 'metadata' is a reserved attribute in SQLAlchemy models (MetaData), so we map it to 'metadata_'
    # or we can use a different name. The DB column can remain 'metadata' if we specify it in mapped_column.
    metadata_: Mapped[Optional[dict[str, Any]]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        nullable=False
    )


class UploadRateLimit(Base):
    """Model for upload rate limits."""
    __tablename__ = "upload_rate_limits"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    # window_start is part of PK.
    # In original schema it was TEXT. Here we can keep it as String to match "Hourly window timestamp" format used in code.
    # Code used: window_start = datetime.utcnow().replace(minute=0, second=0, microsecond=0).isoformat()
    window_start: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    upload_count: Mapped[int] = mapped_column(Integer, default=0)
