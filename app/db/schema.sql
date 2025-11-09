-- Image Processor Database Schema
-- SQLite database for managing processing jobs, events, and rate limits

-- Processing Jobs Table
-- Manages the state machine for image processing jobs
CREATE TABLE IF NOT EXISTS processing_jobs (
    job_id TEXT PRIMARY KEY,
    image_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'retrying')),

    -- Storage information
    storage_bucket TEXT NOT NULL,
    staging_path TEXT,
    processed_paths TEXT,  -- JSON: {variant: path}
    processing_metadata TEXT,  -- JSON: metadata + generated info

    -- Retry mechanism
    attempt_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    last_error TEXT,

    -- Timestamps
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_jobs_status ON processing_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_image ON processing_jobs(image_id);

-- Image Upload Events Table
-- Audit trail for all image-related events
CREATE TABLE IF NOT EXISTS image_upload_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,  -- upload_initiated, processing_started, completed, failed
    image_id TEXT NOT NULL,
    job_id TEXT,
    metadata TEXT,  -- JSON
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_image ON image_upload_events(image_id, created_at DESC);

-- Upload Rate Limits Table
-- Database-enforced rate limiting per user
CREATE TABLE IF NOT EXISTS upload_rate_limits (
    user_id TEXT NOT NULL,
    window_start TEXT NOT NULL,  -- Hourly window timestamp
    upload_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_window ON upload_rate_limits(window_start);
