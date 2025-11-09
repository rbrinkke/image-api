# Image Processor Service Dockerfile
# Production-ready Python 3.11 container with optimized image processing

FROM python:3.11-slim

LABEL maintainer="Image Processor Team"
LABEL description="Domain-agnostic image processing microservice"
LABEL version="1.0.0"

# Set working directory
WORKDIR /app

# Install system dependencies
# - libmagic1: For magic byte file type detection
# - gcc: Required for compiling Python packages
RUN apt-get update && apt-get install -y \
    libmagic1 \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create data directories
RUN mkdir -p /data/storage && \
    chmod -R 755 /data

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/data/processor.db
ENV STORAGE_PATH=/data/storage

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
