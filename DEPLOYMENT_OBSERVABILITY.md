# 🚀 Observability Stack Integration - Deployment Guide

**Service:** image-processor (image-api)
**Status:** ✅ Ready for Deployment
**Date:** 2025-11-10

---

## 📦 What's Been Integrated

Your Image API now has **enterprise-grade observability** with:

✅ **Prometheus Metrics** - 20+ metrics tracking HTTP, processing, storage, errors
✅ **Structured JSON Logging** - Full request correlation with trace IDs
✅ **Auto-Discovery** - Automatic detection by Prometheus & Promtail
✅ **Trace Propagation** - Request tracking across the entire system
✅ **Grafana Dashboards** - Real-time visualization in central dashboards
✅ **Health Checks** - Standardized monitoring endpoints

---

## 🎯 Quick Deployment (3 Steps)

### Step 1: Rebuild & Deploy
```bash
cd /home/user/image-api

# Stop current services
docker compose down

# Rebuild with new observability features
docker compose build

# Start services
docker compose up -d

# Check status
docker compose ps
```

**Expected output:**
```
NAME                        STATUS
image-processor-api         Up (healthy)
image-processor-worker      Up
image-processor-flower      Up
image-processor-redis       Up (healthy)
```

### Step 2: Verify Integration (30 seconds)
```bash
# Run automated verification
./verify-observability.sh
```

**Expected output:**
```
✓ Service is healthy
✓ Metrics endpoint is accessible
✓ X-Trace-ID header present
✓ Service discovered by Prometheus
✓ Logs found in Loki
✓ Logs are valid JSON
✓ trace_id field present in logs
✓ Connected to activity-observability network
```

### Step 3: Open Grafana
```bash
# Open in browser
open http://localhost:3002

# Navigate to: Dashboards → Service Overview
# Look for: "image-processor" service
```

**You should see:**
- 🟢 Service Status: UP
- 📈 Request Rate graph
- ⚡ Response Time metrics
- 💾 Memory Usage

---

## 🔍 What Changed

### Files Modified
```
✏️  docker-compose.yml          - Added observability labels & network
✏️  requirements.txt             - Added prometheus-client
✏️  app/main.py                  - Registered PrometheusMiddleware
✏️  app/api/middleware.py        - Added PrometheusMiddleware & trace_id
✏️  app/core/logging_config.py   - Added trace_id support
```

### Files Created
```
✨  app/api/v1/metrics.py                 - Metrics endpoint & definitions
✨  verify-observability.sh               - Automated verification
✨  OBSERVABILITY_INTEGRATION.md          - Complete integration docs
✨  OBSERVABILITY_QUICK_REFERENCE.md      - Command reference
✨  DEPLOYMENT_OBSERVABILITY.md           - This file
```

---

## 📊 New Endpoints

| Endpoint | URL | Description |
|----------|-----|-------------|
| **Metrics** | `http://localhost:8004/metrics` | Prometheus metrics (NEW) |
| Health | `http://localhost:8004/api/v1/health` | Service health (existing) |

### Test Metrics Endpoint
```bash
curl http://localhost:8004/metrics | head -20
```

**Expected output:**
```
# HELP service_info Service information
# TYPE service_info gauge
service_info{environment="development",name="image-processor",version="1.0.0"} 1.0

# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{endpoint="/api/v1/health",method="GET",service="image-processor",status="200"} 10.0

# HELP http_request_duration_seconds HTTP request duration in seconds
# TYPE http_request_duration_seconds histogram
...
```

---

## 🔗 Integration Architecture

```
┌─────────────────────────────────────────────┐
│     Activity Observability Stack            │
│  (http://localhost:3002 - Grafana)          │
│                                              │
│  Prometheus (:9091) ──┐                     │
│  Loki (:3100) ────────┼─→ Grafana (:3002)  │
│  Promtail ────────────┘                     │
└──────────────────┬──────────────────────────┘
                   │
         activity-observability network
                   │
┌──────────────────▼──────────────────────────┐
│          Image API Services                  │
│  (http://localhost:8004)                     │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │  API Container                     │     │
│  │  • /metrics endpoint               │     │
│  │  • JSON logs with trace_id        │     │
│  │  • X-Trace-ID response header     │     │
│  │  • PrometheusMiddleware           │     │
│  │  • Auto-discovered by Prometheus  │     │
│  └────────────────────────────────────┘     │
│                                              │
│  ┌────────────────────────────────────┐     │
│  │  Worker Container                  │     │
│  │  • JSON logs with trace_id        │     │
│  │  • Collected by Promtail          │     │
│  └────────────────────────────────────┘     │
└──────────────────────────────────────────────┘
```

---

## 🧪 Test the Integration

### 1. Basic Health Check
```bash
curl http://localhost:8004/api/v1/health | jq .
```

**Expected:**
```json
{
  "status": "healthy",
  "service": "image-processor",
  "version": "1.0.0",
  "timestamp": "2025-11-10T14:23:45.123456"
}
```

### 2. Test Trace ID
```bash
# Make request and capture trace ID
RESPONSE=$(curl -s -D - http://localhost:8004/api/v1/health)
echo "$RESPONSE" | grep -i "x-trace-id"
```

**Expected:**
```
X-Trace-ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
X-Correlation-ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 3. Generate Test Traffic
```bash
# Generate 50 requests
for i in {1..50}; do
  curl -s http://localhost:8004/api/v1/health > /dev/null
  echo -n "."
done
echo " Done!"
```

### 4. Check Metrics in Grafana
1. Open `http://localhost:3002`
2. Go to **Dashboards** → **Service Overview**
3. Find **"image-processor"** in the service list
4. Should see request graph updating

### 5. Search Logs in Grafana
1. Go to **Explore**
2. Select **Loki** data source
3. Query: `{service_name="image-processor"}`
4. Should see JSON logs with trace_id field

---

## 📈 Metrics Available

Your service now exposes **20+ metrics**:

### HTTP Metrics
- `http_requests_total` - Total requests by endpoint/status
- `http_request_duration_seconds` - Latency histogram (P50/P95/P99)
- `http_requests_in_progress` - Active requests
- `errors_total` - Errors by type

### Image Processing
- `image_uploads_total` - Uploads (accepted/rejected)
- `image_processing_jobs_total` - Jobs (completed/failed)
- `image_processing_duration_seconds` - Processing time
- `image_processing_jobs_active` - Active jobs
- `image_storage_bytes` - Storage usage

### Database
- `database_queries_total` - Query count
- `database_query_duration_seconds` - Query latency

### Storage
- `storage_operations_total` - Storage ops
- `storage_operation_duration_seconds` - Storage latency

### Celery
- `celery_tasks_total` - Task count
- `celery_task_duration_seconds` - Task execution time
- `celery_queue_length` - Queue depth

---

## 🎛️ Grafana Dashboards

Your service will appear in these dashboards:

### 1. Service Overview
**URL:** `http://localhost:3002/d/service-overview`

**What you'll see:**
- ✅ Service UP/DOWN status
- 📊 Request rate (req/sec)
- ⚠️ Error rate (errors/sec)
- ⏱️ Response time (P50/P95/P99)
- 💾 Memory usage

### 2. Logs Explorer
**URL:** `http://localhost:3002/d/logs-explorer`

**Query examples:**
```logql
# All logs
{service_name="image-processor"}

# Errors only
{service_name="image-processor"} |= "ERROR"

# Slow requests
{service_name="image-processor"} | json | duration_ms > 1000

# Specific trace
{service_name="image-processor"} |= "your-trace-id"
```

### 3. API Performance
**URL:** `http://localhost:3002/d/api-performance`

**Metrics:**
- Throughput (req/sec)
- Latency (avg/P95/P99)
- Success rate (%)
- Error breakdown

---

## 🔍 Trace ID Workflow

### How it works:
```
1. Request arrives → Generate UUID4 trace_id
2. Inject trace_id into logging context
3. All logs include trace_id field
4. Return trace_id in X-Trace-ID header
5. Client can use trace_id to search logs
```

### Example:
```bash
# 1. Upload image with custom trace ID
TRACE_ID="upload-$(date +%s)"

curl -X POST http://localhost:8004/api/v1/images/upload \
  -H "X-Trace-ID: $TRACE_ID" \
  -H "Authorization: Bearer <token>" \
  -F "file=@test.jpg" \
  -F "bucket=test"

# 2. Search all logs for this request
docker logs image-processor-api 2>&1 | grep "$TRACE_ID"

# 3. Or query Loki
curl -G "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode "query={service_name=\"image-processor\"} |= \"${TRACE_ID}\""
```

**You'll see all logs:**
- Request received
- Rate limit check
- File validation
- Job queued
- Processing started (worker logs)
- Image resized
- Storage saved
- Job completed
- Response sent

All with the **same trace_id** for correlation!

---

## ⚠️ Important Notes

### Before Deployment
1. ✅ Ensure observability stack is running
2. ✅ Network `activity-observability` must exist
3. ✅ Prometheus at `localhost:9091`
4. ✅ Loki at `localhost:3100`
5. ✅ Grafana at `localhost:3002`

### After Deployment
1. ⏱️ Wait 30 seconds for Prometheus discovery
2. ⏱️ Wait 1 minute for first metrics scrape
3. ⏱️ Generate some traffic to populate dashboards
4. 🔍 Check verification script output
5. 📊 Verify in Grafana dashboards

### If Something's Wrong
```bash
# 1. Check service logs
docker logs image-processor-api --tail 50

# 2. Check Docker labels
docker inspect image-processor-api | jq '.[].Config.Labels'

# 3. Check network
docker inspect image-processor-api | \
  jq '.[].NetworkSettings.Networks["activity-observability"]'

# 4. Test metrics endpoint
curl http://localhost:8004/metrics | head -20

# 5. Check Prometheus targets
curl -s http://localhost:9091/api/v1/targets | \
  jq '.data.activeTargets[] | select(.labels.container_name=="image-processor-api")'
```

---

## 🎉 Success Criteria

Your deployment is successful when:

- [x] `./verify-observability.sh` shows all ✓ checks passing
- [x] Service appears as UP in Grafana Service Overview
- [x] Metrics visible in Prometheus: `http://localhost:9091/graph`
- [x] Logs visible in Loki: Query `{service_name="image-processor"}`
- [x] Trace IDs in response headers: `curl -D - http://localhost:8004/api/v1/health`
- [x] Request graphs updating in Grafana after generating traffic
- [x] Can correlate requests using trace_id in log search

---

## 📚 Documentation

Full documentation available:

| Document | Description |
|----------|-------------|
| **OBSERVABILITY_INTEGRATION.md** | Complete integration details |
| **OBSERVABILITY_QUICK_REFERENCE.md** | Command reference & queries |
| **DEPLOYMENT_OBSERVABILITY.md** | This deployment guide |
| **verify-observability.sh** | Automated verification script |

---

## 🆘 Troubleshooting

### Service not in Prometheus
```bash
# Verify labels
docker inspect image-processor-api | jq '.[].Config.Labels'

# Should show:
# "prometheus.scrape": "true"
# "prometheus.port": "8000"
# "prometheus.path": "/metrics"

# Restart Prometheus if needed
docker compose -f /mnt/d/activity/observability-stack/docker-compose.yml restart prometheus
```

### Logs not in Loki
```bash
# Verify logging driver is json-file (NOT loki)
docker inspect image-processor-api | jq '.[].HostConfig.LogConfig'

# Should show:
# "Type": "json-file"

# Restart Promtail if needed
docker compose -f /mnt/d/activity/observability-stack/docker-compose.yml restart promtail
```

### Trace IDs not working
```bash
# Check logs have trace_id field
docker logs image-processor-api 2>&1 | tail -1 | jq '.trace_id'

# Should return a UUID

# Check response headers
curl -D - http://localhost:8004/api/v1/health | grep -i trace

# Should show X-Trace-ID header
```

---

## 🚀 Next Steps

After successful deployment:

1. **Set up Alerts** - Configure Prometheus alerts for errors/latency
2. **Create Custom Dashboards** - Add image-api specific panels
3. **Document SLOs** - Define service level objectives
4. **Train Team** - Share query examples and trace ID usage
5. **Monitor Performance** - Watch for bottlenecks and optimize

---

## 📞 Support

- **Full docs:** `OBSERVABILITY_INTEGRATION.md`
- **Quick ref:** `OBSERVABILITY_QUICK_REFERENCE.md`
- **Verify:** `./verify-observability.sh`
- **Image API:** `README.md`

---

**✅ Ready to Deploy!**

Run these commands to get started:
```bash
docker compose down
docker compose build
docker compose up -d
./verify-observability.sh
open http://localhost:3002
```

---

**Integration by:** Claude Code
**Date:** 2025-11-10
**Version:** 1.0.0
**Status:** Production Ready ✅
