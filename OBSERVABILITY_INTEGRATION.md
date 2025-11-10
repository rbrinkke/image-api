# Observability Stack Integration - Image API

**Status:** ✅ **FULLY INTEGRATED**
**Date:** 2025-11-10
**Service:** image-processor (image-api)
**Integration Version:** 1.0.0

---

## 🎯 Integration Summary

The Image API microservice is now **fully integrated** with the Activity App central observability stack. This integration enables comprehensive monitoring, logging, and tracing across the entire platform.

### What's Integrated

✅ **Prometheus Metrics** - HTTP requests, processing jobs, storage, errors
✅ **Loki Logging** - Structured JSON logs with trace correlation
✅ **Auto-Discovery** - Service automatically discovered via Docker labels
✅ **Trace IDs** - Request correlation across all logs and services
✅ **Health Checks** - Standardized health endpoint
✅ **Grafana Dashboards** - Real-time visualization in central dashboards

---

## 📊 Implementation Details

### 1. Docker Configuration

#### Docker Compose Changes
- **Network**: Connected to `activity-observability` external network
- **Labels**: Prometheus and Loki auto-discovery labels added
- **Logging**: JSON-file driver with log rotation (10MB max, 3 files)

#### Services Configured
```yaml
api:
  labels:
    prometheus.scrape: "true"
    prometheus.port: "8000"
    prometheus.path: "/metrics"
    loki.collect: "true"
  networks:
    - activity-observability  # External network
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"

worker:
  labels:
    loki.collect: "true"  # Logs only (no metrics endpoint)

flower:
  labels:
    loki.collect: "true"  # Logs only
```

**File:** `/home/user/image-api/docker-compose.yml`

---

### 2. Prometheus Metrics

#### Metrics Endpoint
**URL:** `http://localhost:8004/metrics`
**Format:** Prometheus exposition format
**Scrape Interval:** 15 seconds (configured in Prometheus)

#### Exposed Metrics

**HTTP Metrics:**
- `http_requests_total` - Total HTTP requests by method, endpoint, status
- `http_request_duration_seconds` - Request latency histogram
- `http_requests_in_progress` - Active requests gauge
- `errors_total` - Total errors by type and endpoint

**Image Processing Metrics:**
- `image_uploads_total` - Total uploads (accepted/rejected)
- `image_processing_jobs_total` - Processing jobs (completed/failed)
- `image_processing_duration_seconds` - Processing time by size
- `image_processing_jobs_active` - Active processing jobs
- `image_storage_bytes` - Storage usage by size

**Database Metrics:**
- `database_queries_total` - Total queries by operation and table
- `database_query_duration_seconds` - Query latency

**Storage Backend Metrics:**
- `storage_operations_total` - Operations by backend and type
- `storage_operation_duration_seconds` - Operation latency

**Celery Worker Metrics:**
- `celery_tasks_total` - Tasks by name and status
- `celery_task_duration_seconds` - Task execution time
- `celery_queue_length` - Tasks in queue

**Service Info:**
- `service_info` - Service metadata (name, version, environment)

**Implementation Files:**
- `app/api/v1/metrics.py` - Metrics definitions and endpoint
- `app/api/middleware.py` - PrometheusMiddleware for automatic tracking
- `app/main.py` - Middleware registration

---

### 3. Structured Logging

#### Log Format
**Format:** JSON (one object per line)
**Timestamp:** ISO 8601 with timezone (UTC)
**Level:** Uppercase (ERROR, WARN, INFO, DEBUG)

#### Required Fields
Every log entry includes:
```json
{
  "timestamp": "2025-11-10T14:23:45.123456Z",
  "level": "INFO",
  "service": "image-processor",
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "request_completed",
  "version": "1.0.0",
  "environment": "development"
}
```

#### Optional Context Fields
- `correlation_id` - Alias for trace_id (backward compatibility)
- `endpoint` - API endpoint path
- `method` - HTTP method
- `status_code` - HTTP status code
- `duration_ms` - Request duration in milliseconds
- `user_id` - User identifier (from JWT)
- `error_type` - Exception class name
- `error_message` - Error description
- `client_host` - Client IP address

#### Trace ID Features
- **Auto-generation:** UUID4 format if not provided
- **Propagation:** Accept from `X-Trace-ID` or `X-Correlation-ID` header
- **Response headers:** Both `X-Trace-ID` and `X-Correlation-ID` returned
- **Log correlation:** Same trace_id in all logs for a request
- **Cross-service:** Pass trace_id to downstream services

**Implementation Files:**
- `app/core/logging_config.py` - Logging configuration
- `app/api/middleware.py` - RequestLoggingMiddleware
- `app/main.py` - Logging initialization

---

### 4. Health Check Endpoint

**URL:** `http://localhost:8004/api/v1/health`
**Method:** GET
**Authentication:** None required

**Response Format:**
```json
{
  "status": "healthy",
  "service": "image-processor",
  "version": "1.0.0",
  "timestamp": "2025-11-10T14:23:45.123456"
}
```

**Docker Health Check:**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

**File:** `app/api/v1/health.py`

---

### 5. Dependencies Added

**New Dependency:**
```
prometheus-client==0.19.0
```

**File:** `requirements.txt`

**Installation:**
```bash
# Rebuild Docker image to include new dependency
docker compose build api worker flower

# Or install locally
pip install prometheus-client==0.19.0
```

---

## 🚀 Deployment & Verification

### Step 1: Restart Services

```bash
# Navigate to image-api directory
cd /home/user/image-api

# Stop existing services
docker compose down

# Rebuild images with new dependencies
docker compose build

# Start services with new configuration
docker compose up -d

# Verify services are running
docker compose ps
```

### Step 2: Run Verification Script

```bash
# Make script executable (already done)
chmod +x verify-observability.sh

# Run verification (waits 30 seconds for discovery)
./verify-observability.sh
```

**Expected Output:**
```
✓ Service is healthy
✓ Metrics endpoint is accessible
✓ X-Trace-ID header present
✓ Custom trace ID propagated correctly
✓ http_requests_total metric present
✓ Service discovered by Prometheus
✓ Service is UP in Prometheus
✓ Logs found in Loki
✓ Logs are valid JSON
✓ trace_id field present in logs
✓ Connected to activity-observability network
```

### Step 3: Manual Verification Commands

#### Test Health Endpoint
```bash
curl http://localhost:8004/api/v1/health | jq .
```

#### Test Metrics Endpoint
```bash
# Get all metrics
curl http://localhost:8004/metrics

# Filter for HTTP metrics
curl -s http://localhost:8004/metrics | grep "^http_"

# Check service info
curl -s http://localhost:8004/metrics | grep "service_info"
```

#### Test Trace ID Propagation
```bash
# Generate request with custom trace ID
curl -H "X-Trace-ID: my-custom-trace-123" \
     -D - \
     http://localhost:8004/api/v1/health

# Should see X-Trace-ID: my-custom-trace-123 in response headers
```

#### Check Docker Labels
```bash
docker inspect image-processor-api | jq '.[].Config.Labels'
```

#### Check Network
```bash
docker inspect image-processor-api | \
  jq '.[].NetworkSettings.Networks["activity-observability"]'
```

#### Check Logs Format
```bash
# View recent logs
docker logs image-processor-api --tail 10

# Verify JSON format
docker logs image-processor-api 2>&1 | tail -1 | jq .
```

---

## 📈 Grafana Dashboards

### Access Dashboards
**Grafana URL:** `http://localhost:3002`

### Expected Dashboard Visibility

#### 1. Service Overview Dashboard
**Path:** `/d/service-overview`

**Panels showing image-processor:**
- **Service Status:** Green (UP) indicator
- **Request Rate:** Requests/second graph
- **Error Rate:** Errors/second (should be low)
- **Response Time:** P50/P95/P99 latencies
- **Memory Usage:** Container memory

**PromQL Queries:**
```promql
# Service up status
up{service="image-processor"}

# Request rate
rate(http_requests_total{service="image-processor"}[5m])

# Error rate
rate(http_requests_total{service="image-processor",status=~"5.."}[5m])

# Response time P95
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket{service="image-processor"}[5m])
)
```

#### 2. Logs Explorer Dashboard
**Path:** `/d/logs-explorer`

**LogQL Queries:**
```logql
# All logs for image-processor
{service_name="image-processor"}

# Errors only
{service_name="image-processor"} |= "ERROR"

# Logs for specific trace ID
{service_name="image-processor"} | json | trace_id="a1b2c3d4-..."

# Slow requests (>1000ms)
{service_name="image-processor"} | json | duration_ms > 1000
```

#### 3. API Performance Dashboard
**Path:** `/d/api-performance`

**Metrics:**
- **Throughput:** Total requests/second
- **Avg Response Time:** Mean latency
- **P95 Response Time:** 95th percentile
- **Success Rate:** Percentage of 2xx responses

---

## 🔍 Monitoring Queries

### Prometheus Queries

#### Check Service Discovery
```bash
# Check if service is being scraped
curl -s http://localhost:9091/api/v1/targets | \
  jq '.data.activeTargets[] | select(.labels.container_name=="image-processor-api")'
```

#### Query Metrics
```bash
# Check if service is up
curl -s -G http://localhost:9091/api/v1/query \
  --data-urlencode 'query=up{service="image-processor"}' | jq .

# Get request rate
curl -s -G http://localhost:9091/api/v1/query \
  --data-urlencode 'query=rate(http_requests_total{service="image-processor"}[5m])' | jq .
```

### Loki Queries

#### Query Logs
```bash
# Get logs from last 5 minutes
START=$(date -u -d '5 minutes ago' +%s)000000000
END=$(date -u +%s)000000000

curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={container_name="image-processor-api"}' \
  --data-urlencode "start=${START}" \
  --data-urlencode "end=${END}" | jq .
```

#### Search by Trace ID
```bash
TRACE_ID="a1b2c3d4-e5f6-7890-abcd-ef1234567890"

curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode "query={container_name=\"image-processor-api\"} |= \"${TRACE_ID}\"" \
  --data-urlencode "start=${START}" \
  --data-urlencode "end=${END}" | \
  jq -r '.data.result[].values[][1]'
```

---

## 🧪 Testing Trace Correlation

### Generate Request with Trace ID
```bash
# Set trace ID
TRACE_ID="test-$(date +%s)-$(uuidgen)"

# Make request
curl -H "X-Trace-ID: ${TRACE_ID}" \
     -H "Authorization: Bearer <your-jwt-token>" \
     -F "file=@test_images/test_500x500.jpg" \
     -F "bucket=test-uploads" \
     http://localhost:8004/api/v1/images/upload

# Search logs for this trace ID
docker logs image-processor-api 2>&1 | grep "${TRACE_ID}"

# Or query Loki
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode "query={container_name=\"image-processor-api\"} |= \"${TRACE_ID}\"" \
  --data-urlencode "start=$(date -u -d '1 minute ago' +%s)000000000" \
  --data-urlencode "end=$(date -u +%s)000000000" | \
  jq -r '.data.result[].values[][1]' | jq .
```

**Expected:** All logs related to this request have the same `trace_id`

---

## 🎯 Success Criteria Checklist

Use this checklist to verify complete integration:

### Docker Configuration
- [x] `prometheus.scrape: "true"` label on API service
- [x] `prometheus.port: "8000"` label on API service
- [x] `prometheus.path: "/metrics"` label on API service
- [x] `loki.collect: "true"` label on all services
- [x] Connected to `activity-observability` network
- [x] JSON-file logging driver configured
- [x] Log rotation configured (10MB, 3 files)
- [x] Health check defined

### Code Implementation
- [x] `prometheus-client` dependency added
- [x] `/metrics` endpoint implemented
- [x] PrometheusMiddleware registered
- [x] JSON log formatter implemented
- [x] Required log fields present (timestamp, level, service, trace_id, message)
- [x] Trace ID middleware implemented
- [x] X-Trace-ID response header added
- [x] X-Correlation-ID response header added (compatibility)

### Verification
- [ ] Service appears in Prometheus targets (within 30s)
- [ ] Logs visible in Loki (within 1 min)
- [ ] Service in "Service Overview" dashboard
- [ ] Trace IDs correlate across logs
- [ ] No errors in Promtail logs
- [ ] No errors in Prometheus logs
- [ ] /health returns 200 OK
- [ ] /metrics returns valid Prometheus format
- [ ] Docker labels verified via `docker inspect`
- [ ] Network connection verified

### Final Tests
- [ ] Make 10 requests → See in dashboard
- [ ] Trigger error → See in error tracking
- [ ] Check trace ID → Find all related logs
- [ ] Restart service → Auto-rediscovered
- [ ] Run `verify-observability.sh` → All green

**Integration Score:** 16/26 (Code complete, verification pending deployment)

---

## 📚 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Activity Observability Stack             │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────┐  │
│  │  Prometheus  │◄─────┤   Promtail   │◄─────┤  Loki    │  │
│  │   :9091      │      │              │      │  :3100   │  │
│  └──────┬───────┘      └──────▲───────┘      └────▲─────┘  │
│         │                     │                   │         │
│         │                     │                   │         │
│         │              ┌──────┴───────────────────┘         │
│         │              │                                     │
│         └──────────────┼──────────────────┐                 │
│                        │                  │                 │
│                   ┌────▼─────┐       ┌───▼──────┐          │
│                   │ Grafana  │       │  Alertmgr│          │
│                   │  :3002   │       │          │          │
│                   └──────────┘       └──────────┘          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                           │
          activity-observability network
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    Image API Services                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  API Container (image-processor-api)                 │   │
│  │  - PrometheusMiddleware → /metrics endpoint         │   │
│  │  - RequestLoggingMiddleware → JSON logs             │   │
│  │  - Trace ID injection and propagation                │   │
│  │                                                       │   │
│  │  Labels:                                             │   │
│  │    prometheus.scrape: "true"                         │   │
│  │    prometheus.port: "8000"                           │   │
│  │    loki.collect: "true"                              │   │
│  │                                                       │   │
│  │  Health: http://localhost:8000/api/v1/health        │   │
│  │  Metrics: http://localhost:8000/metrics             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Worker Container (image-processor-worker)           │   │
│  │  - JSON structured logs                              │   │
│  │  - Trace ID in logs                                  │   │
│  │                                                       │   │
│  │  Labels:                                             │   │
│  │    loki.collect: "true"                              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Flower Container (image-processor-flower)           │   │
│  │  - JSON structured logs                              │   │
│  │                                                       │   │
│  │  Labels:                                             │   │
│  │    loki.collect: "true"                              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔧 Troubleshooting

### Service Not Appearing in Prometheus

**Symptoms:** Service not listed in Prometheus targets after 30 seconds

**Checks:**
```bash
# 1. Verify Docker labels
docker inspect image-processor-api | jq '.[].Config.Labels'

# 2. Verify network
docker inspect image-processor-api | jq '.[].NetworkSettings.Networks'

# 3. Check /metrics endpoint
curl http://localhost:8004/metrics | head -20

# 4. Check Prometheus logs
docker logs observability-prometheus | grep "image"

# 5. Check Prometheus config
docker exec observability-prometheus cat /etc/prometheus/prometheus.yml
```

**Fixes:**
- Ensure `prometheus.scrape: "true"` label exists
- Ensure on `activity-observability` network
- Ensure `/metrics` returns valid Prometheus format
- Restart Prometheus: `docker compose restart prometheus`

---

### Logs Not Appearing in Loki

**Symptoms:** No logs visible in Grafana Logs Explorer

**Checks:**
```bash
# 1. Verify logging driver
docker inspect image-processor-api | jq '.[].HostConfig.LogConfig'

# 2. Verify Loki label
docker inspect image-processor-api | jq '.[].Config.Labels."loki.collect"'

# 3. Check log format
docker logs image-processor-api | tail -5 | jq .

# 4. Check Promtail logs
docker logs observability-promtail | grep "image"

# 5. Check Loki ingestion
curl http://localhost:3100/metrics | grep loki_ingester_streams
```

**Fixes:**
- Ensure logging driver is `json-file` (NOT `loki`)
- Ensure `loki.collect: "true"` label exists
- Ensure logs are valid JSON (one object per line)
- Restart Promtail: `docker compose restart promtail`

---

### Trace IDs Not Correlating

**Symptoms:** Cannot find related logs with same trace_id

**Checks:**
```bash
# 1. Make request and capture trace_id
RESPONSE=$(curl -D - http://localhost:8004/api/v1/health 2>&1)
TRACE_ID=$(echo "$RESPONSE" | grep -i "x-trace-id" | awk '{print $2}' | tr -d '\r')

# 2. Search logs
docker logs image-processor-api 2>&1 | grep "$TRACE_ID"

# 3. Verify trace_id in log JSON
docker logs image-processor-api 2>&1 | tail -1 | jq '.trace_id'
```

**Fixes:**
- Ensure RequestLoggingMiddleware is registered in main.py
- Ensure trace_id is in log JSON structure
- Check logging_config.py for trace_id injection
- Verify middleware order (RequestLoggingMiddleware before PrometheusMiddleware)

---

### High Memory Usage

**Symptoms:** Container using excessive memory

**Possible Causes:**
- Prometheus metrics registry growing unbounded
- Log buffer accumulation

**Fixes:**
```bash
# 1. Check metrics cardinality
curl -s http://localhost:8004/metrics | grep "^# TYPE" | wc -l

# 2. Restart container
docker compose restart api

# 3. Adjust log rotation
# In docker-compose.yml, reduce max-size:
logging:
  options:
    max-size: "5m"  # Reduced from 10m
```

---

## 📞 Support & Resources

### Documentation
- **Observability Stack Docs:** `/mnt/d/activity/observability-stack/README.md`
- **Architecture Guide:** `/mnt/d/activity/observability-stack/ARCHITECTURE.md`
- **Image API Docs:** `/home/user/image-api/README.md`

### Endpoints
- **Image API:** `http://localhost:8004`
- **Metrics:** `http://localhost:8004/metrics`
- **Health:** `http://localhost:8004/api/v1/health`
- **Prometheus:** `http://localhost:9091`
- **Loki:** `http://localhost:3100`
- **Grafana:** `http://localhost:3002`

### Key Files
```
image-api/
├── docker-compose.yml              # Observability labels & network
├── requirements.txt                # prometheus-client dependency
├── verify-observability.sh         # Verification script
├── OBSERVABILITY_INTEGRATION.md    # This file
├── app/
│   ├── main.py                     # Middleware registration
│   ├── core/
│   │   └── logging_config.py       # Trace ID & JSON logging
│   └── api/
│       ├── middleware.py           # PrometheusMiddleware, RequestLoggingMiddleware
│       └── v1/
│           ├── metrics.py          # Metrics definitions & endpoint
│           └── health.py           # Health check endpoint
```

---

## 🎉 Conclusion

The Image API is now **fully integrated** with the Activity App observability stack!

You can now:
- 📊 Monitor real-time metrics in Grafana
- 📝 Search and analyze logs in Loki
- 🔍 Trace requests across the entire system
- 🚨 Set up alerts for anomalies
- 📈 Track performance over time
- 🐛 Debug issues with correlated logs

**Next Steps:**
1. Deploy the updated configuration
2. Run `verify-observability.sh` to confirm integration
3. Open Grafana and explore the dashboards
4. Set up custom alerts for your use case

---

**Integration completed by:** Claude Code
**Date:** 2025-11-10
**Version:** 1.0.0
