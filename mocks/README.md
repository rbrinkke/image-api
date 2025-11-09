# Mock Servers for Image Processing API

Professional-quality mock servers for testing and development without external dependencies.

## 📋 Overview

This directory contains production-ready FastAPI mock servers that simulate external services and clients for the image processing API:

1. **S3 Mock Server** - AWS S3-compatible storage (Priority 1)
2. **Client Application Mock** - Web UI demonstrating API integration (Priority 2)
3. **Webhook Receiver Mock** - Event notification receiver (Priority 3)

## 🚀 Quick Start

### Run Individual Mocks

```bash
# Install dependencies
cd mocks
pip install -r requirements.txt

# Run S3 mock (port 9000)
python s3_mock.py

# Run client app (port 3000)
python client_app_mock.py

# Run webhook receiver (port 4000)
python webhook_receiver_mock.py
```

### Run All Mocks with Docker Compose

```bash
# Start all mock servers
cd mocks
docker compose -f docker-compose.mocks.yml up -d

# View logs
docker compose -f docker-compose.mocks.yml logs -f

# Stop all mocks
docker compose -f docker-compose.mocks.yml down
```

## 📦 Mock Servers

### 1. S3 Mock Server (Port 9000)

AWS S3-compatible mock for testing storage operations without AWS.

**Features:**
- ✅ Upload objects (PUT /{bucket}/{key})
- ✅ Download objects (GET /{bucket}/{key})
- ✅ Delete objects (DELETE /{bucket}/{key})
- ✅ Object metadata (HEAD /{bucket}/{key})
- ✅ Presigned URL generation
- ✅ Server-side encryption simulation
- ✅ Admin endpoints for inspection

**Endpoints:**
```bash
# Upload object
curl -X PUT http://localhost:9000/test-bucket/image.jpg \
  -F "file=@test_image.jpg"

# Download object
curl http://localhost:9000/test-bucket/image.jpg -o downloaded.jpg

# Delete object
curl -X DELETE http://localhost:9000/test-bucket/image.jpg

# Get presigned URL
curl "http://localhost:9000/presigned-url?bucket=test-bucket&key=image.jpg&expires_in=3600"

# Admin: List all buckets
curl http://localhost:9000/admin/buckets

# Admin: List objects in bucket
curl http://localhost:9000/admin/objects/test-bucket

# Admin: Clear all data
curl -X DELETE http://localhost:9000/admin/reset

# OpenAPI docs
open http://localhost:9000/docs
```

**Integration with Image API:**

Update `.env` to use S3 mock:
```bash
STORAGE_BACKEND=s3
AWS_ENDPOINT_URL=http://localhost:9000  # Point to mock
AWS_REGION=eu-west-1
AWS_ACCESS_KEY_ID=test-key
AWS_SECRET_ACCESS_KEY=test-secret
```

---

### 2. Client Application Mock (Port 3000)

Interactive web UI demonstrating image API integration with real-time job polling.

**Features:**
- ✅ Drag-drop image upload interface
- ✅ Automatic JWT token generation
- ✅ Real-time job status polling
- ✅ Result visualization (all variants)
- ✅ Stress testing (rate limit validation)
- ✅ Upload history tracking
- ✅ Live logging console

**Access:**
```bash
# Open web UI
open http://localhost:3000

# Generate JWT token
curl http://localhost:3000/api/generate-token?user_id=test-user-123

# Upload image programmatically
curl -X POST http://localhost:3000/api/upload \
  -F "file=@image.jpg" \
  -F "bucket=test-uploads" \
  -F "user_id=user-456" \
  -F "context=demo"

# Check job status
curl http://localhost:3000/api/status/{job_id}

# Get final result
curl http://localhost:3000/api/result/{job_id}

# Run stress test (51 uploads)
curl -X POST http://localhost:3000/api/stress-test \
  -F "user_id=test-user-123" \
  -F "count=51"

# View upload history
curl http://localhost:3000/api/history

# OpenAPI docs
open http://localhost:3000/docs
```

**Configuration:**
```bash
export IMAGE_API_URL=http://localhost:8002
export JWT_SECRET=dev-secret-change-in-production
export PORT=3000
```

---

### 3. Webhook Receiver Mock (Port 4000)

Mock webhook endpoint for testing event notifications with HMAC signature verification.

**Features:**
- ✅ Receive and log webhook events
- ✅ HMAC-SHA256 signature verification
- ✅ Event filtering and search
- ✅ Event replay to another URL
- ✅ Real-time dashboard UI
- ✅ Per-client statistics

**Access:**
```bash
# Open dashboard
open http://localhost:4000

# Send webhook event
curl -X POST http://localhost:4000/webhooks/client-123 \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: <hmac-signature>" \
  -d '{
    "event_type": "image.processed",
    "image_id": "uuid-123",
    "job_id": "uuid-456",
    "status": "completed",
    "urls": {...}
  }'

# List all events
curl http://localhost:4000/webhooks/events

# Filter events by client
curl "http://localhost:4000/webhooks/events?client_id=client-123"

# Get specific event
curl http://localhost:4000/webhooks/events/{event_id}

# Clear all events
curl -X DELETE http://localhost:4000/webhooks/events

# Replay event to another URL
curl -X POST "http://localhost:4000/webhooks/replay/{event_id}?target_url=https://example.com/webhook"

# Get statistics
curl http://localhost:4000/webhooks/stats

# OpenAPI docs
open http://localhost:4000/docs
```

**Generate HMAC Signature:**
```python
import hmac
import hashlib
import json

payload = {"event_type": "image.processed", "image_id": "123"}
secret = "webhook-secret-123"
signature = hmac.new(
    secret.encode(),
    json.dumps(payload).encode(),
    hashlib.sha256
).hexdigest()
print(f"X-Webhook-Signature: {signature}")
```

---

## 🧪 Testing & Integration

### Integration Test Examples

Located in `/mocks/examples/`:

```bash
# Test S3 mock integration
python examples/s3_integration_test.py

# Test complete upload workflow
python examples/upload_workflow_test.py

# Test webhook integration
python examples/webhook_test.py
```

### Unit Tests

Located in `/mocks/tests/`:

```bash
# Run all mock server tests
pytest mocks/tests/

# Test specific mock
pytest mocks/tests/test_s3_mock.py -v

# Run with coverage
pytest mocks/tests/ --cov=mocks --cov-report=html
```

---

## 🏗️ Architecture

### Directory Structure

```
mocks/
├── README.md                      # This file
├── requirements.txt               # Python dependencies
├── docker-compose.mocks.yml       # Docker orchestration
├── Dockerfile.mocks               # Docker image
├── common/                        # Shared utilities
│   ├── __init__.py
│   ├── base.py                    # FastAPI app factory
│   ├── auth.py                    # JWT helpers
│   ├── models.py                  # Pydantic models
│   └── errors.py                  # Error handling
├── s3_mock.py                     # S3 mock server
├── client_app_mock.py             # Client application
├── webhook_receiver_mock.py       # Webhook receiver
├── tests/                         # Unit tests
│   ├── test_s3_mock.py
│   ├── test_client_app.py
│   └── test_webhook_receiver.py
└── examples/                      # Integration examples
    ├── s3_integration_test.py
    ├── upload_workflow_test.py
    └── webhook_test.py
```

### Common Utilities

All mocks use shared utilities from `/mocks/common/`:

**`base.py`**: FastAPI app factory
```python
from mocks.common.base import create_mock_app

app = create_mock_app(
    title="My Mock API",
    description="Mock server for testing",
    version="1.0.0"
)
```

**`auth.py`**: JWT generation/validation
```python
from mocks.common.auth import generate_test_jwt, verify_test_jwt

# Generate token
token = generate_test_jwt(user_id="user-123", expires_minutes=60)

# Verify token
payload = verify_test_jwt(token)
user_id = payload["sub"]
```

**`errors.py`**: Standardized error responses
```python
from mocks.common.errors import NotFoundError, ValidationError

raise NotFoundError("Object", "bucket/key")
raise ValidationError("Invalid file format", {"allowed": ["jpg", "png"]})
```

**`models.py`**: Shared Pydantic models
```python
from mocks.common.models import ProcessingResult, UploadRequest

result = ProcessingResult(
    job_id="uuid-123",
    image_id="uuid-456",
    status="completed",
    urls={...}
)
```

---

## 🔧 Configuration

### Environment Variables

**S3 Mock:**
```bash
PORT=9000
PRESIGNED_URL_BASE=http://localhost:9000
```

**Client App:**
```bash
PORT=3000
IMAGE_API_URL=http://localhost:8002
JWT_SECRET=dev-secret-change-in-production
```

**Webhook Receiver:**
```bash
PORT=4000
WEBHOOK_SECRET=webhook-secret-123
```

### Docker Compose Configuration

Edit `docker-compose.mocks.yml` to customize ports, environment variables, or add new mocks.

---

## 📊 Use Cases

### 1. S3 Storage Testing

Test storage backend switching without AWS account:

```bash
# Start S3 mock
python s3_mock.py

# Update image API config to use mock
# In .env or docker-compose.yml:
AWS_ENDPOINT_URL=http://localhost:9000

# Upload image via image API
# Files will be stored in S3 mock instead of AWS
```

### 2. Client Integration Examples

Use client app as reference implementation:

```bash
# Start client app
python client_app_mock.py

# Open http://localhost:3000
# Upload image through UI
# See complete workflow: JWT → Upload → Poll → Display
```

### 3. Webhook Development

Develop webhook notifications before building the feature:

```bash
# Start webhook receiver
python webhook_receiver_mock.py

# Send test webhooks from image API (future feature)
# View events in dashboard: http://localhost:4000
# Validate payload format and signatures
```

### 4. Load Testing

Test rate limiting with stress test:

```bash
# Open client app: http://localhost:3000
# Click "Stress Test (50 uploads)"
# Observe rate limiting after 50th upload
# Check dashboard: http://localhost:8002/dashboard
```

---

## 🎯 Best Practices

### Development Workflow

1. **Start mocks first**: `docker compose -f docker-compose.mocks.yml up -d`
2. **Configure API**: Update `.env` to point to mocks
3. **Run tests**: Integration tests use mocks instead of real services
4. **Develop features**: Test against mocks for fast iteration
5. **Verify production**: Switch to real services for final validation

### Testing Guidelines

- **Unit tests**: Mock external dependencies
- **Integration tests**: Use mock servers (S3, webhooks)
- **E2E tests**: Use client app mock for full workflow
- **Load tests**: Use stress test endpoints

### Debugging Tips

```bash
# View S3 mock storage
curl http://localhost:9000/admin/buckets

# Check webhook events
curl http://localhost:4000/webhooks/events

# Monitor client upload history
curl http://localhost:3000/api/history

# View all mock logs
docker compose -f docker-compose.mocks.yml logs -f
```

---

## 🔒 Security Notes

- **JWT Secret**: Default is `dev-secret-change-in-production` (development only)
- **Webhook Secret**: Default is `webhook-secret-123` (development only)
- **CORS**: Enabled with `allow_origins=["*"]` (development only)
- **Production**: Never use these mocks in production environments

---

## 📚 Additional Resources

- **Image API Documentation**: See `/CLAUDE.md`
- **OpenAPI Docs**: Each mock has `/docs` endpoint
- **Dashboard**: Image API dashboard at `http://localhost:8002/dashboard`
- **Flower**: Celery monitoring at `http://localhost:5555`

---

## 🐛 Troubleshooting

### S3 Mock Issues

```bash
# Check if S3 mock is running
curl http://localhost:9000/health

# View stored objects
curl http://localhost:9000/admin/buckets

# Clear all data and restart
curl -X DELETE http://localhost:9000/admin/reset
```

### Client App Issues

```bash
# Check connection to image API
curl http://localhost:8002/api/v1/health

# Verify JWT secret matches
# Client app JWT_SECRET must match API JWT_SECRET_KEY

# Check logs
docker compose -f docker-compose.mocks.yml logs client-app
```

### Webhook Receiver Issues

```bash
# Test webhook endpoint
curl -X POST http://localhost:4000/webhooks/test-client \
  -H "Content-Type: application/json" \
  -d '{"event_type":"test","data":"hello"}'

# Verify signature generation
python -c "import hmac, hashlib; print(hmac.new(b'webhook-secret-123', b'{\"test\":1}', hashlib.sha256).hexdigest())"
```

---

## 🚀 Future Enhancements

Planned mock servers (Priority 4-6):

- **Auth Provider Mock** - OAuth2/OIDC provider for JWT federation testing
- **Image Analysis Mock** - ML-based analysis (object detection, NSFW, faces)
- **Redis Mock** - Lightweight Redis for unit testing

---

## 📝 License

Part of the Image Processing API project. See main repository for license details.

---

**Built with FastAPI, Pydantic, and professional software engineering practices.**
