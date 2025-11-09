# Mock Servers - Quick Start Guide

## 🎯 30-Second Setup

```bash
cd /home/user/image-api/mocks

# Install dependencies
pip install -r requirements.txt

# Run all mocks
python s3_mock.py &
python client_app_mock.py &
python webhook_receiver_mock.py &

# Or use Docker
docker compose -f docker-compose.mocks.yml up -d
```

## 📍 Access Points

| Service | URL | Description |
|---------|-----|-------------|
| **S3 Mock** | http://localhost:9000 | S3-compatible storage |
| **S3 Docs** | http://localhost:9000/docs | OpenAPI documentation |
| **Client App** | http://localhost:3000 | Upload UI with drag-drop |
| **Client Docs** | http://localhost:3000/docs | OpenAPI documentation |
| **Webhook Receiver** | http://localhost:4000 | Event notification dashboard |
| **Webhook Docs** | http://localhost:4000/docs | OpenAPI documentation |

## 🧪 Quick Tests

### S3 Mock
```bash
# Health check
curl http://localhost:9000/health

# Upload file
curl -X PUT http://localhost:9000/test-bucket/file.txt \
  -F "file=@test.txt"

# Download file
curl http://localhost:9000/test-bucket/file.txt

# List buckets
curl http://localhost:9000/stats
```

### Client App
```bash
# Generate JWT token
curl http://localhost:3000/api/generate-token?user_id=test-123

# Open upload UI
open http://localhost:3000
```

### Webhook Receiver
```bash
# Send test webhook
curl -X POST http://localhost:4000/webhooks/test-client \
  -H "Content-Type: application/json" \
  -d '{"event_type":"test","data":"hello"}'

# View events
curl http://localhost:4000/webhooks/events

# Open dashboard
open http://localhost:4000
```

## 🔧 Integration with Image API

Update image API `.env`:
```bash
# Use S3 mock instead of AWS
STORAGE_BACKEND=s3
AWS_ENDPOINT_URL=http://localhost:9000
AWS_ACCESS_KEY_ID=test-key
AWS_SECRET_ACCESS_KEY=test-secret
AWS_REGION=eu-west-1
```

## 📊 Run Integration Tests

```bash
# Test S3 integration
python examples/s3_integration_test.py

# Test upload workflow (requires image API running)
python examples/upload_workflow_test.py ../test_images/test_500x500.jpg

# Test webhooks
python examples/webhook_test.py
```

## 🐳 Docker Commands

```bash
# Start all mocks
docker compose -f docker-compose.mocks.yml up -d

# View logs
docker compose -f docker-compose.mocks.yml logs -f

# Stop all
docker compose -f docker-compose.mocks.yml down

# Restart specific mock
docker compose -f docker-compose.mocks.yml restart s3-mock
```

## 💡 Common Use Cases

### Test Storage Backend Switching
```bash
# 1. Start S3 mock
python s3_mock.py &

# 2. Configure image API to use mock (see above)

# 3. Upload image via image API
# Files go to S3 mock instead of AWS!
```

### Test Rate Limiting
```bash
# 1. Open client app
open http://localhost:3000

# 2. Click "Stress Test (50 uploads)"

# 3. Observe rate limiting after 50th request

# 4. Check dashboard
open http://localhost:8002/dashboard
```

### Develop Webhook Feature
```bash
# 1. Start webhook receiver
python webhook_receiver_mock.py &

# 2. Open dashboard
open http://localhost:4000

# 3. Send test webhooks from your code
# 4. View events in real-time dashboard
```

## 📚 Full Documentation

- **Comprehensive Guide**: `README.md`
- **Implementation Details**: `IMPLEMENTATION_SUMMARY.md`
- **Integration Tests**: `examples/`

## ⚡ Troubleshooting

### S3 Mock Won't Start
```bash
# Check dependencies
pip install -r requirements.txt

# Check port availability
lsof -i :9000

# View logs
tail -f /tmp/s3_mock.log
```

### Client App Can't Connect to API
```bash
# Verify image API is running
curl http://localhost:8002/api/v1/health

# Check JWT secret matches
# Client: JWT_SECRET=dev-secret-change-in-production
# API: JWT_SECRET_KEY=dev-secret-change-in-production
```

### Webhook Signature Failing
```bash
# Generate correct signature in Python:
import hmac, hashlib, json
payload = {"event_type": "test"}
secret = "webhook-secret-123"
sig = hmac.new(secret.encode(), json.dumps(payload).encode(), hashlib.sha256).hexdigest()
print(f"X-Webhook-Signature: {sig}")
```

---

**For detailed documentation, see `README.md`**
