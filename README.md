# Image Processor Service

**A production-ready, domain-agnostic microservice for intelligent image processing**

## 🚀 Overview

Image Processor is a standalone FastAPI-based microservice designed to handle image uploads, processing, and retrieval with enterprise-grade reliability. Built with a metadata-driven architecture, it processes images through EXIF stripping, multi-size generation, and modern format conversion while maintaining complete separation from your application's business logic.

### ✨ Key Features

- **🎯 Domain-Agnostic**: No knowledge of users, activities, or business entities - pure utility service
- **📦 Standalone**: Self-contained with embedded SQLite database and local/S3 storage
- **⚡ Async-First**: Non-blocking API with Celery workers for CPU-intensive processing
- **☁️ Storage-Agnostic**: Seamless switching between local filesystem and AWS S3
- **🔒 Production-Ready**: Built-in rate limiting, retry logic, health monitoring, and audit trails

## 📋 Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    FastAPI Gateway                        │
│  • JWT Authentication          • Rate Limiting            │
│  • Content Validation          • Multi-layer Security     │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ├──> SQLite Database (Embedded)
                     │    • processing_jobs (state machine)
                     │    • image_upload_events (audit trail)
                     │    • upload_rate_limits (enforcement)
                     │
                     ├──> Storage Layer (Abstraction)
                     │    • Local Filesystem (development)
                     │    • AWS S3 (production)
                     │
                     └──> Redis (Task Queue)
                          • Celery broker for async jobs

┌──────────────────────────────────────────────────────────┐
│                   Celery Workers                          │
│  • EXIF Metadata Stripping    • Multi-Size Generation    │
│  • WebP Conversion             • Dominant Color Extract   │
│  • Pillow-SIMD Optimized      • Automatic Retry Logic    │
└──────────────────────────────────────────────────────────┘
```

## 🏁 Quick Start

### Prerequisites

- Docker & Docker Compose
- 2GB RAM minimum (4GB recommended)
- 10GB disk space for development

### Installation

```bash
# 1. Clone repository
cd image-processor

# 2. Create environment file
cp .env.example .env

# Edit .env and set:
# JWT_SECRET_KEY=your-secure-random-key-here

# 3. Start services
docker-compose up -d

# 4. Verify health
curl http://localhost:8000/api/v1/health

# 5. View API documentation
open http://localhost:8000/docs

# 6. Monitor Celery workers
open http://localhost:5555  # Flower dashboard
```

### Test Upload

```bash
# Generate test JWT
export TEST_TOKEN=$(python3 -c "
import jwt
print(jwt.encode(
    {'sub': 'test-user-123'},
    'dev-secret-change-in-production',
    algorithm='HS256'
))
")

# Upload test image
curl -X POST http://localhost:8000/api/v1/images/upload \
  -H "Authorization: Bearer $TEST_TOKEN" \
  -F "file=@test-photo.jpg" \
  -F "bucket=test-uploads" \
  -F "metadata={\"context\":\"test_upload\"}"

# Response:
# {
#   "job_id": "abc-123...",
#   "image_id": "def-456...",
#   "status_url": "/api/v1/images/jobs/abc-123..."
# }

# Check status (repeat until completed)
curl http://localhost:8000/api/v1/images/jobs/abc-123...

# Get processed results
curl http://localhost:8000/api/v1/images/jobs/abc-123.../result
```

## 📁 Project Structure

```
image-processor/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py          # Pydantic settings
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.sql         # Database schema
│   │   └── sqlite.py          # Database operations
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── protocol.py        # Storage protocol
│   │   ├── local.py           # Local filesystem backend
│   │   └── s3.py              # AWS S3 backend
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py    # Auth, validation
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── upload.py      # Upload endpoints
│   │       ├── retrieval.py   # Retrieval endpoints
│   │       └── health.py      # Health/monitoring
│   └── tasks/
│       ├── __init__.py
│       ├── celery_app.py      # Celery configuration
│       └── processing.py      # Image processing workers
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

## 🎨 Core Features

### Security-First Design

- **JWT-Based Authentication**: Token validation with configurable secrets
- **Magic Bytes Validation**: Never trust client-provided MIME types
- **EXIF Metadata Stripping**: Removes GPS coordinates, camera info, and potential malicious payloads
- **Content-Length Pre-Check**: Reject oversized uploads before bandwidth consumption
- **Database-Enforced Rate Limiting**: 50 uploads/hour per user (configurable)

### Intelligent Image Processing

**Multi-Size Generation:**
- `thumbnail`: 150px - List/grid views
- `medium`: 600px - Detail views
- `large`: 1200px - Full-screen views
- `original`: 4096px - Backup/archival

**Format Optimization:**
- Automatic WebP conversion (25-35% smaller than JPEG)
- Configurable quality settings (default: 85)
- Aspect ratio preservation across all sizes

**Smart Metadata Extraction:**
- Dominant color calculation for progressive loading placeholders
- Dimension tracking per variant
- File size metrics for bandwidth optimization

## 🔌 API Endpoints

### Upload Image

```bash
POST /api/v1/images/upload
Content-Type: multipart/form-data
Authorization: Bearer {jwt_token}

Parameters:
  - file: binary (required)
  - bucket: string (required)
  - metadata: json (optional)

Response (202 Accepted):
{
  "job_id": "uuid",
  "image_id": "uuid",
  "status_url": "/api/v1/images/jobs/{job_id}",
  "message": "Upload accepted. Processing initiated."
}
```

### Check Status

```bash
GET /api/v1/images/jobs/{job_id}

Response:
{
  "job_id": "uuid",
  "image_id": "uuid",
  "status": "completed",
  "created_at": "2024-11-08T10:00:00Z",
  "completed_at": "2024-11-08T10:00:05Z"
}
```

### Get Results

```bash
GET /api/v1/images/jobs/{job_id}/result

Response:
{
  "image_id": "uuid",
  "status": "completed",
  "urls": {
    "thumbnail": "/storage/bucket/processed/thumbnail/uuid_thumbnail.webp",
    "medium": "/storage/bucket/processed/medium/uuid_medium.webp",
    "large": "/storage/bucket/processed/large/uuid_large.webp",
    "original": "/storage/bucket/processed/original/uuid_original.webp"
  },
  "metadata": {
    "dominant_color": "#3A5F8C",
    "variants": { ... }
  }
}
```

## ⚙️ Configuration

### Environment Variables

See `.env.example` for all available configuration options:

- `JWT_SECRET_KEY`: Secret for JWT validation (**CHANGE IN PRODUCTION!**)
- `STORAGE_BACKEND`: `local` or `s3`
- `RATE_LIMIT_MAX_UPLOADS`: Uploads per hour per user
- `MAX_UPLOAD_SIZE_MB`: Maximum file size
- `WEBP_QUALITY`: WebP compression quality (0-100)

### Migration to S3

```bash
# Change one line in .env:
STORAGE_BACKEND=s3
AWS_REGION=eu-west-1

# Restart services
docker-compose restart

# All new uploads go to S3 - zero code changes needed!
```

## 📊 Monitoring

- **Health**: `GET /api/v1/health`
- **Stats**: `GET /api/v1/health/stats`
- **Failed Jobs**: `GET /api/v1/health/failed`
- **Flower UI**: `http://localhost:5555`

## 🚀 Production Deployment

1. **Set secure JWT_SECRET_KEY** (use `openssl rand -hex 32`)
2. **Configure CORS origins** (in `app/main.py`)
3. **Use S3 for storage** (set `STORAGE_BACKEND=s3`)
4. **Set up reverse proxy** (Nginx/Traefik with HTTPS)
5. **Scale workers** (`docker-compose up --scale worker=4`)

## 📈 Performance

- **Processing**: < 5s for typical mobile photo (2-3MB)
- **Pillow-SIMD**: 4-6x faster than stock Pillow
- **WebP**: 25-35% smaller than JPEG at same quality

## 🤝 Contributing

Contributions welcome! This is a production-ready service built with best practices.

## 📄 License

MIT License

---

**Built with ❤️ for developers who need reliable image processing without the complexity.**
