# Image Processor Service Dockerfile
# Production-ready Python 3.11 container with optimized image processing
# Security: Multi-stage build, non-root user, minimal attack surface

# =============================================================================
# Stage 1: Builder - Compile dependencies
# =============================================================================
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for cleaner dependency isolation
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Stage 2: Runtime - Minimal production image
# =============================================================================
FROM python:3.11-slim

LABEL maintainer="Image Processor Team"
LABEL description="Domain-agnostic image processing microservice"
LABEL version="1.0.0"

# Install only runtime dependencies (no gcc/build tools)
# - libmagic1: For magic byte file type detection
# - curl: For health checks
# - tini: For proper signal handling (PID 1 zombie reaping)
RUN apt-get update && apt-get install -y \
    libmagic1 \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set working directory
WORKDIR /app

# Copy application code
COPY app/ ./app/

# Create non-root user and group
# - UID/GID 1000 for compatibility with most systems
# - No login shell for security
# - Home directory for potential caching
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/false -m appuser

# Create data directories with proper ownership
RUN mkdir -p /data/storage && \
    chown -R appuser:appuser /app /data

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/processor.db \
    STORAGE_PATH=/data/storage \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check (running as non-root user)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Use tini as entrypoint for proper signal handling
# This ensures graceful shutdown and prevents zombie processes
ENTRYPOINT ["/usr/bin/tini", "--"]

# Production command - NO --reload flag
# For multiple workers, use: --workers 4
# For Kubernetes/Cloud Run, keep workers=1 and scale horizontally
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-config", "/dev/null"]
