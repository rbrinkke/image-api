# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ultra-minimalistic, domain-agnostic image processing service. Built with **FastAPI** (Python), **SQLite** (embedded database), **Redis** (message broker), and **Celery** (async workers). Features intelligent image processing, multi-size generation, WebP conversion, EXIF stripping, and JWT authentication.

## Common Commands

### Development

```bash
# Start all services (Redis, API, Workers, Flower)
docker compose up -d

# View API logs
docker compose logs -f api

# View worker logs
docker compose logs -f worker

# Run API locally (without Docker)
cd /mnt/d/activity/image-api
export $(cat .env | xargs)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Access services
open http://localhost:8000/docs      # API documentation
open http://localhost:8000/dashboard # Technical monitoring dashboard
open http://localhost:5555            # Flower (Celery monitoring)
```

### Testing

```bash
# Run quick verification test (14 tests, < 30s)
./test_quick.sh

# Run comprehensive test suite (50+ tests, 2-3 min)
./test_comprehensive.sh

# Run authorization system tests (50+ tests, requires Redis)
./test_authorization.sh

# Run specific test suites (pytest)
pytest tests/test_authorization_cache.py -v      # Cache tests (19 tests)
pytest tests/test_circuit_breaker.py -v          # Circuit breaker (15 tests)
pytest tests/test_authorization_integration.py -v # Integration (15 tests)

# Test health endpoint
curl http://localhost:8000/api/v1/health

# Test with JWT token
export TEST_TOKEN=$(python3 -c "
import jwt
print(jwt.encode(
    {'sub': 'test-user-123'},
    'dev-secret-change-in-production',
    algorithm='HS256'
))
")

curl -X POST http://localhost:8000/api/v1/images/upload \
  -H "Authorization: Bearer $TEST_TOKEN" \
  -F "file=@test_images/test_500x500.jpg" \
  -F "bucket=test-uploads" \
  -F "metadata={\"context\":\"test\"}"
```

### Code Quality

```bash
# Format code
black app/ tests/
isort app/ tests/

# Type checking
mypy app/

# Clean artifacts
docker compose down -v  # Remove volumes
rm -rf __pycache__ .pytest_cache
```

## Architecture Overview

### Backend (FastAPI)

```
app/
├── main.py              # FastAPI app initialization, CORS, lifespan
├── core/                # Core utilities
│   └── config.py        # Pydantic Settings (environment configuration)
├── db/                  # Database layer (SQLite)
│   ├── schema.sql       # Database schema (3 tables)
│   └── sqlite.py        # Async database operations
├── storage/             # Storage abstraction layer
│   ├── protocol.py      # StorageBackend Protocol (interface)
│   ├── local.py         # Local filesystem implementation
│   ├── s3.py            # AWS S3 implementation
│   └── __init__.py      # Factory with lazy S3 loading
├── api/                 # API endpoints
│   ├── dependencies.py  # Auth, validation, rate limiting
│   └── v1/
│       ├── upload.py    # POST /upload, GET /jobs/{id}
│       ├── retrieval.py # GET /{image_id}, DELETE, batch
│       └── health.py    # Health checks, statistics
└── tasks/               # Celery workers
    ├── celery_app.py    # Celery configuration
    └── processing.py    # Image processing workers
```

### Database Schema

All database access through **async SQLite operations** (no ORM):

- `processing_jobs` - State machine for job tracking (pending → processing → completed/failed)
- `image_upload_events` - Audit trail for all events
- `upload_rate_limits` - Per-user hourly rate limit enforcement

See `app/db/schema.sql` for complete definitions.

### Storage Abstraction

Protocol-based design allows seamless switching between storage backends:

- **LocalStorageBackend**: `/data/storage/{bucket}/{path}` - Development/testing
- **S3StorageBackend**: AWS S3 with presigned URLs - Production

Switch backends by changing `STORAGE_BACKEND=s3` in `.env` - zero code changes needed!

### Docker Services

All services orchestrated via `docker-compose.yml`:

- **api**: FastAPI backend (port 8000)
- **worker**: Celery workers (4 concurrent)
- **redis**: Message broker (port 6379)
- **flower**: Celery monitoring UI (port 5555)

## Key Workflows

### Image Processing Flow

1. **Upload**: Client → POST /api/v1/images/upload → JWT validation → Rate limit check → Magic bytes validation → Save to staging
2. **Queue**: Create job in database → Queue Celery task → Return 202 Accepted with job_id
3. **Processing** (Celery Worker):
   - Strip EXIF metadata (security + privacy)
   - Extract dominant color (progressive loading placeholder)
   - Generate 4 variants (thumbnail/medium/large/original)
   - Convert all to WebP (quality: 85)
   - Save to processed paths
   - Update job status: completed
4. **Retrieval**: Client → GET /api/v1/images/{image_id}?size=medium → Return URL

### Multi-Size Generation

All images processed into 4 variants maintaining aspect ratio:
- **thumbnail**: 150px - List/grid views
- **medium**: 600px - Detail views
- **large**: 1200px - Full-screen views
- **original**: 4096px - Backup/archival

### Storage Backend Migration

```bash
# Local → S3 migration (zero code changes)
# 1. Update .env:
STORAGE_BACKEND=s3
AWS_REGION=eu-west-1
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret

# 2. Restart services
docker compose restart

# All new uploads go to S3!
```

## API Endpoints

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| POST | `/api/v1/images/upload` | JWT | Upload image for processing |
| GET | `/api/v1/images/jobs/{job_id}` | No | Check job status |
| GET | `/api/v1/images/jobs/{job_id}/result` | No | Get processed results |
| GET | `/api/v1/images/{image_id}` | No | Get image URL by ID (specific size) |
| GET | `/api/v1/images/{image_id}/all` | No | Get all variant URLs |
| GET | `/api/v1/images/{image_id}/direct` | No | Direct file serving or redirect |
| DELETE | `/api/v1/images/{image_id}` | JWT | Delete all variants |
| GET | `/api/v1/images/batch` | No | Batch retrieval (max 50) |
| GET | `/api/v1/health` | No | Basic health check |
| GET | `/api/v1/health/stats` | No | Comprehensive statistics |
| GET | `/api/v1/health/failed` | No | Recent failed jobs |

## Configuration

### Environment Variables (.env)

Critical settings:
- `JWT_SECRET_KEY`: MUST change in production (min 32 chars) - `openssl rand -hex 32`
- `STORAGE_BACKEND`: `local` or `s3`
- `STORAGE_PATH`: Local storage path (default: `/data/storage`)
- `DATABASE_PATH`: SQLite database path (default: `/data/processor.db`)
- `REDIS_URL`: Redis connection (default: `redis://redis:6379/0`)
- `RATE_LIMIT_MAX_UPLOADS`: Uploads per hour per user (default: 50)
- `MAX_UPLOAD_SIZE_MB`: Maximum file size (default: 10)
- `WEBP_QUALITY`: WebP compression quality 0-100 (default: 85)
- `ALLOWED_MIME_TYPES`: JSON array of allowed types

See `.env.example` for all options.

### Docker Compose Services

- **api**: FastAPI backend (port 8000, health checks, hot reload)
- **worker**: Celery workers (4 concurrent, automatic restart)
- **redis**: Redis 7-alpine (AOF persistence, health checks)
- **flower**: Monitoring UI (port 5555)
- **Volumes**: `processor_data` (DB + images), `redis_data` (persistence)

## Technical Dashboard

**Comprehensive real-time monitoring and troubleshooting interface**

Access: `http://localhost:8000/dashboard`

### Features

- **Auto-refresh**: 5-second updates with countdown indicator
- **System Resources**: CPU, memory, disk usage with progress bars
- **Database Health**: Connection status, size, table counts, recent activity
- **Redis Status**: Memory, connections, queue lengths, ops/sec
- **Celery Workers**: Active workers, task counts, registered tasks
- **Processing Metrics**: Jobs by status, performance stats (1h/24h), recent jobs
- **Storage Info**: Backend type, disk usage (local), file counts
- **Rate Limiting**: Users near limit, active windows
- **Error Tracking**: Recent failures, error summary, patterns
- **Configuration**: Current settings (non-sensitive)

### Dashboard API

```bash
# Get all metrics as JSON
curl http://localhost:8000/dashboard/data | jq .

# Monitor specific metrics
curl -s http://localhost:8000/dashboard/data | jq '.celery.workers.active'
curl -s http://localhost:8000/dashboard/data | jq '.errors.error_summary.last_hour'
curl -s http://localhost:8000/dashboard/data | jq '.redis.queue_lengths.celery'
```

### Quick Troubleshooting

**Images not processing?**
1. Check Celery workers active: Dashboard → Celery Workers
2. Check Redis queue length: Dashboard → Redis Status
3. Check recent failures: Dashboard → Recent Failures

**Slow processing?**
1. Check avg processing time: Dashboard → Processing Metrics
2. Check system resources: Dashboard → System Resources
3. Check worker count vs queue length

**High failure rate?**
1. Review recent failures: Dashboard → Recent Failures
2. Check error patterns in error messages
3. Verify storage disk space: Dashboard → Storage Info

See `DASHBOARD.md` for complete documentation.

## Security Features

1. **JWT Authentication**: Token validation for upload/delete operations
2. **Magic Bytes Validation**: Never trust client MIME types - uses `python-magic`
3. **Content-Length Pre-Check**: Rejects oversized uploads before processing
4. **EXIF Metadata Stripping**: Removes GPS, camera info, potential malicious payloads
5. **Database-Enforced Rate Limiting**: 50 uploads/hour per user (configurable)
6. **Retry Logic**: 3 attempts with 60s delay for failed processing
7. **Audit Trail**: All events logged in `image_upload_events` table
8. **Storage Encryption**: S3 server-side encryption (AES256)
9. **Presigned URLs**: 1-hour expiration for S3 access
10. **Generic Error Messages**: No information leakage

## Troubleshooting

**Database connection errors:**
```bash
docker compose ps api
docker compose logs api | grep -i database
# Check: DATABASE_PATH=/data/processor.db (mounted volume)
```

**Redis connection errors:**
```bash
docker compose ps redis
docker exec image-processor-redis redis-cli ping
# Expected: PONG
```

**Worker not processing:**
```bash
docker compose logs worker | grep -i ready
# Check Celery workers are ready
curl http://localhost:5555  # Flower UI
```

**Check processing jobs:**
```bash
# Access database
docker exec -it image-processor-api sqlite3 /data/processor.db
SELECT job_id, status, last_error FROM processing_jobs WHERE status = 'failed' LIMIT 10;
```

**Storage issues:**
```bash
# Local storage
docker exec image-processor-api ls -lah /data/storage/

# S3 storage (check AWS credentials)
docker compose logs api | grep -i s3
```

**Rate limit debugging:**
```bash
# Check rate limits
docker exec -it image-processor-api sqlite3 /data/processor.db
SELECT user_id, window_start, upload_count FROM upload_rate_limits;
```

## Testing Specific Scenarios

```bash
# Test image upload flow
export TOKEN=$(python3 -c "import jwt; print(jwt.encode({'sub': 'user-123'}, 'dev-secret-change-in-production', algorithm='HS256'))")

# Upload
RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/images/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_images/test_500x500.jpg" \
  -F "bucket=test-uploads" \
  -F "metadata={\"context\":\"test\"}")

JOB_ID=$(echo $RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['job_id'])")

# Poll status (repeat until completed)
curl http://localhost:8000/api/v1/images/jobs/$JOB_ID

# Get results
curl http://localhost:8000/api/v1/images/jobs/$JOB_ID/result | python3 -m json.tool

# Test rate limiting (send 51 requests quickly)
for i in {1..51}; do
  curl -X POST http://localhost:8000/api/v1/images/upload \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@test_images/test_500x500.jpg" \
    -F "bucket=test-uploads"
  echo "Request $i"
done
# Expected: 429 Too Many Requests on 51st request

# Test invalid file type
echo "not an image" > fake.txt
curl -X POST http://localhost:8000/api/v1/images/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@fake.txt" \
  -F "bucket=test-uploads"
# Expected: 415 Unsupported Media Type

# Test batch retrieval
IMAGE_IDS="uuid1,uuid2,uuid3"
curl "http://localhost:8000/api/v1/images/batch?image_ids=$IMAGE_IDS"
```

## Important Implementation Details

### Why Protocol-Based Storage?
- **Separation of concerns**: Storage logic isolated from business logic
- **Easy migration**: Change one line in .env to switch backends
- **Testing**: Easy to mock for unit tests
- **Future-proof**: Can add GCS, Azure Blob, or custom backends

### Why SQLite Instead of PostgreSQL?
- **Embedded**: No separate database service required
- **Sufficient**: < 10k images/day workload
- **Simple deployment**: Single file database
- **Atomic operations**: Built-in ACID compliance
- **Migration path**: Can switch to PostgreSQL if needed

### Why Celery for Processing?
- **CPU-intensive**: Image processing blocks async event loop
- **Distributed**: Can scale workers horizontally
- **Retry logic**: Built-in retry mechanisms
- **Monitoring**: Flower provides real-time insights
- **Task queue**: Fair distribution of work

### Why EXIF Stripping?
- **Privacy**: Removes GPS coordinates, timestamps
- **Security**: Removes potential malicious payloads
- **Consistency**: All images have same metadata format
- **File size**: Reduces size by removing unnecessary data

### Why WebP Format?
- **Compression**: 25-35% smaller than JPEG at same quality
- **Quality**: Better than JPEG at low bitrates
- **Browser support**: 95%+ modern browsers
- **Future-proof**: Google-backed format

### Why Multiple Sizes?
- **Bandwidth**: Serve appropriate size for viewport
- **UX**: Faster load times for thumbnails
- **Responsive**: Support different screen densities
- **Flexibility**: Applications can choose optimal size

### Why Dominant Color Extraction?
- **Progressive loading**: Show color placeholder while loading
- **UX**: Smooth loading experience
- **Design**: Use color in UI (borders, shadows)
- **Minimal cost**: Simple 1x1 resize operation

## Test Suite Structure

```
test_quick.sh           # 14 tests, < 30s (health, upload, processing, retrieval)
test_comprehensive.sh   # 50+ tests, 2-3 min (full coverage)
test_images/            # 8 test images (JPEG, PNG, WebP)
  ├── test_500x500.jpg
  ├── test_800x600.jpg
  ├── test_large_3024x2268.jpg
  └── ...
```

## Performance Considerations

- **Processing Time**: < 5s for typical mobile photo (2-3MB)
- **Pillow-SIMD**: Uncomment in requirements.txt for 4-6x speedup (requires AVX2 CPU)
- **Worker Scaling**: Scale workers with `docker compose up --scale worker=8`
- **Redis Persistence**: AOF enabled for durability
- **SQLite Performance**: WAL mode enabled for concurrent reads
- **Storage**: Local for development, S3 for production

## Documentation Files

- `README.md`: Quick start, features, API reference
- `CLAUDE.md`: This file - development guide
- `DASHBOARD.md`: Technical dashboard documentation
- `DEPLOYMENT_SUCCESS.md`: Deployment verification report
- `app/db/schema.sql`: Complete database schema
- `.env.example`: Configuration template
- `docker-compose.yml`: Service orchestration
