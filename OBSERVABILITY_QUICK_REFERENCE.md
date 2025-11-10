# Observability Stack - Quick Reference Guide

**Service:** image-processor (image-api)
**Status:** ✅ Fully Integrated

---

## 🚀 Quick Start

### Deploy Updated Configuration
```bash
cd /home/user/image-api
docker compose down
docker compose build
docker compose up -d
```

### Verify Integration
```bash
./verify-observability.sh
```

---

## 🔗 Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Image API | `http://localhost:8004` | Main API |
| Health Check | `http://localhost:8004/api/v1/health` | Health endpoint |
| Metrics | `http://localhost:8004/metrics` | Prometheus metrics |
| Prometheus | `http://localhost:9091` | Metrics database |
| Loki | `http://localhost:3100` | Logs database |
| Grafana | `http://localhost:3002` | Dashboards |

---

## 📊 Prometheus Queries

### Service Health
```promql
# Is service up?
up{service="image-processor"}

# Number of service instances
count(up{service="image-processor"})
```

### HTTP Requests
```promql
# Total requests
http_requests_total{service="image-processor"}

# Requests per second (5m average)
rate(http_requests_total{service="image-processor"}[5m])

# Requests by status code
sum by (status) (rate(http_requests_total{service="image-processor"}[5m]))
```

### Response Times
```promql
# Average response time
rate(http_request_duration_seconds_sum{service="image-processor"}[5m])
  /
rate(http_request_duration_seconds_count{service="image-processor"}[5m])

# P50 (median)
histogram_quantile(0.50,
  rate(http_request_duration_seconds_bucket{service="image-processor"}[5m])
)

# P95 (95th percentile)
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket{service="image-processor"}[5m])
)

# P99 (99th percentile)
histogram_quantile(0.99,
  rate(http_request_duration_seconds_bucket{service="image-processor"}[5m])
)
```

### Error Rates
```promql
# Total errors
errors_total{service="image-processor"}

# Error rate (errors/sec)
rate(errors_total{service="image-processor"}[5m])

# HTTP error rate (5xx responses)
rate(http_requests_total{service="image-processor",status=~"5.."}[5m])

# Error rate as percentage
(
  rate(http_requests_total{service="image-processor",status=~"5.."}[5m])
  /
  rate(http_requests_total{service="image-processor"}[5m])
) * 100
```

### Image Processing
```promql
# Processing jobs completed
image_processing_jobs_total{service="image-processor",status="completed"}

# Processing jobs failed
image_processing_jobs_total{service="image-processor",status="failed"}

# Active processing jobs
image_processing_jobs_active{service="image-processor"}

# Average processing time
rate(image_processing_duration_seconds_sum{service="image-processor"}[5m])
  /
rate(image_processing_duration_seconds_count{service="image-processor"}[5m])
```

### System Resources
```promql
# Container memory usage
container_memory_usage_bytes{name="image-processor-api"}

# Container CPU usage
rate(container_cpu_usage_seconds_total{name="image-processor-api"}[5m])
```

---

## 📝 Loki Queries (LogQL)

### Basic Queries
```logql
# All logs
{container_name="image-processor-api"}

# Logs by service name
{service_name="image-processor"}

# Last 5 minutes
{container_name="image-processor-api"} |> now() - 5m
```

### Filter by Level
```logql
# Errors only
{service_name="image-processor"} |= "ERROR"

# Warnings and errors
{service_name="image-processor"} |~ "ERROR|WARN"

# Info and above (exclude DEBUG)
{service_name="image-processor"} != "DEBUG"
```

### JSON Field Filters
```logql
# Parse JSON and filter
{service_name="image-processor"} | json | level="ERROR"

# Filter by endpoint
{service_name="image-processor"} | json | endpoint="/api/v1/images/upload"

# Filter by status code
{service_name="image-processor"} | json | status_code="500"

# Slow requests (>1000ms)
{service_name="image-processor"} | json | duration_ms > 1000
```

### Trace ID Correlation
```logql
# Find all logs for a specific trace ID
{service_name="image-processor"} |= "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# Using JSON parsing
{service_name="image-processor"}
  | json
  | trace_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### Aggregations
```logql
# Count logs per minute
sum(count_over_time({service_name="image-processor"}[1m]))

# Error count per minute
sum(count_over_time({service_name="image-processor"} |= "ERROR" [1m]))

# Requests per endpoint
sum by (endpoint) (
  count_over_time(
    {service_name="image-processor"}
    | json
    | endpoint != ""
    [5m]
  )
)
```

---

## 🧪 cURL Test Commands

### Health Check
```bash
curl http://localhost:8004/api/v1/health | jq .
```

### Metrics
```bash
# Get all metrics
curl http://localhost:8004/metrics

# HTTP metrics only
curl -s http://localhost:8004/metrics | grep "^http_"

# Service info
curl -s http://localhost:8004/metrics | grep "service_info"
```

### Trace ID Test
```bash
# Request with custom trace ID
curl -H "X-Trace-ID: test-$(date +%s)" \
     -D - \
     http://localhost:8004/api/v1/health

# Should see X-Trace-ID in response headers
```

### Generate Test Traffic
```bash
# 100 requests for metrics
for i in {1..100}; do
  curl -s http://localhost:8004/api/v1/health > /dev/null
  echo "Request $i"
  sleep 0.1
done
```

### Image Upload with Trace ID
```bash
# Generate JWT token
export TOKEN=$(python3 -c "
import jwt
print(jwt.encode(
    {'sub': 'test-user-123'},
    'dev-secret-change-in-production',
    algorithm='HS256'
))
")

# Generate trace ID
TRACE_ID="upload-test-$(date +%s)"

# Upload with trace ID
curl -X POST http://localhost:8004/api/v1/images/upload \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Trace-ID: $TRACE_ID" \
  -F "file=@test_images/test_500x500.jpg" \
  -F "bucket=test-uploads" \
  -F "metadata={\"context\":\"observability-test\"}"

# Find logs for this upload
docker logs image-processor-api 2>&1 | grep "$TRACE_ID"
```

---

## 🐳 Docker Commands

### View Logs
```bash
# API logs (last 100 lines)
docker logs image-processor-api --tail 100

# Follow API logs in real-time
docker logs -f image-processor-api

# Worker logs
docker logs image-processor-worker --tail 50

# Filter for errors
docker logs image-processor-api 2>&1 | grep "ERROR"

# JSON formatted log
docker logs image-processor-api 2>&1 | tail -1 | jq .
```

### Check Configuration
```bash
# Docker labels
docker inspect image-processor-api | jq '.[].Config.Labels'

# Network membership
docker inspect image-processor-api | \
  jq '.[].NetworkSettings.Networks["activity-observability"]'

# Logging configuration
docker inspect image-processor-api | jq '.[].HostConfig.LogConfig'

# Health check
docker inspect image-processor-api | jq '.[].State.Health'
```

### Service Management
```bash
# Restart API only
docker compose restart api

# Restart all services
docker compose restart

# View service status
docker compose ps

# View resource usage
docker stats image-processor-api --no-stream
```

---

## 🔍 Prometheus API Queries

### Check Service Discovery
```bash
# All active targets
curl -s http://localhost:9091/api/v1/targets | jq .

# Image API target specifically
curl -s http://localhost:9091/api/v1/targets | \
  jq '.data.activeTargets[] | select(.labels.container_name=="image-processor-api")'

# Check if service is up
curl -s -G http://localhost:9091/api/v1/query \
  --data-urlencode 'query=up{service="image-processor"}' | \
  jq '.data.result'
```

### Query Metrics
```bash
# Request rate
curl -s -G http://localhost:9091/api/v1/query \
  --data-urlencode 'query=rate(http_requests_total{service="image-processor"}[5m])' | \
  jq '.data.result'

# Error count
curl -s -G http://localhost:9091/api/v1/query \
  --data-urlencode 'query=sum(errors_total{service="image-processor"})' | \
  jq '.data.result[].value[1]'
```

---

## 🔍 Loki API Queries

### Query Logs
```bash
# Set time range (last 5 minutes)
START=$(date -u -d '5 minutes ago' +%s)000000000
END=$(date -u +%s)000000000

# Get logs
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={container_name="image-processor-api"}' \
  --data-urlencode "start=${START}" \
  --data-urlencode "end=${END}" \
  --data-urlencode "limit=10" | \
  jq -r '.data.result[].values[][1]' | jq .
```

### Search by Trace ID
```bash
TRACE_ID="your-trace-id-here"

curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode "query={container_name=\"image-processor-api\"} |= \"${TRACE_ID}\"" \
  --data-urlencode "start=${START}" \
  --data-urlencode "end=${END}" | \
  jq -r '.data.result[].values[][1]' | jq .
```

### Count Errors
```bash
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query=sum(count_over_time({container_name="image-processor-api"} |= "ERROR" [5m]))' \
  --data-urlencode "start=${START}" \
  --data-urlencode "end=${END}" | \
  jq '.data.result'
```

---

## 📈 Common Monitoring Scenarios

### Scenario 1: Service is Slow
```bash
# 1. Check response times in Prometheus
curl -s -G http://localhost:9091/api/v1/query \
  --data-urlencode 'query=histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service="image-processor"}[5m]))' | \
  jq '.data.result[].value[1]'

# 2. Find slow requests in logs
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={service_name="image-processor"} | json | duration_ms > 1000' \
  --data-urlencode "start=$(date -u -d '15 minutes ago' +%s)000000000" \
  --data-urlencode "end=$(date -u +%s)000000000" | \
  jq -r '.data.result[].values[][1]' | jq .

# 3. Check resource usage
docker stats image-processor-api --no-stream
```

### Scenario 2: Errors Occurring
```bash
# 1. Check error rate
curl -s -G http://localhost:9091/api/v1/query \
  --data-urlencode 'query=rate(errors_total{service="image-processor"}[5m])' | \
  jq '.data.result'

# 2. View recent errors in logs
docker logs image-processor-api 2>&1 | grep "ERROR" | tail -10 | jq .

# 3. Group errors by type
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={service_name="image-processor"} |= "ERROR"' \
  --data-urlencode "start=$(date -u -d '1 hour ago' +%s)000000000" \
  --data-urlencode "end=$(date -u +%s)000000000" | \
  jq -r '.data.result[].values[][1]' | jq -r '.error_type' | sort | uniq -c
```

### Scenario 3: Trace a Specific Request
```bash
# 1. Make request with trace ID
TRACE_ID="debug-$(date +%s)"
curl -H "X-Trace-ID: $TRACE_ID" http://localhost:8004/api/v1/health

# 2. Find all logs for this request
docker logs image-processor-api 2>&1 | grep "$TRACE_ID" | jq .

# 3. Query Loki for the trace
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode "query={container_name=\"image-processor-api\"} |= \"${TRACE_ID}\"" \
  --data-urlencode "start=$(date -u -d '5 minutes ago' +%s)000000000" \
  --data-urlencode "end=$(date -u +%s)000000000" | \
  jq -r '.data.result[].values[][1]' | jq .
```

---

## 🚨 Alert Examples

### Prometheus Alert Rules

**High Error Rate:**
```yaml
- alert: HighErrorRate
  expr: |
    (
      rate(http_requests_total{service="image-processor",status=~"5.."}[5m])
      /
      rate(http_requests_total{service="image-processor"}[5m])
    ) * 100 > 5
  for: 5m
  labels:
    severity: warning
    service: image-processor
  annotations:
    summary: "High error rate in image-processor"
    description: "Error rate is {{ $value }}% (threshold: 5%)"
```

**Slow Response Times:**
```yaml
- alert: SlowResponseTime
  expr: |
    histogram_quantile(0.95,
      rate(http_request_duration_seconds_bucket{service="image-processor"}[5m])
    ) > 2
  for: 5m
  labels:
    severity: warning
    service: image-processor
  annotations:
    summary: "Slow response times in image-processor"
    description: "P95 latency is {{ $value }}s (threshold: 2s)"
```

**Service Down:**
```yaml
- alert: ServiceDown
  expr: up{service="image-processor"} == 0
  for: 1m
  labels:
    severity: critical
    service: image-processor
  annotations:
    summary: "image-processor service is down"
    description: "Service has been down for more than 1 minute"
```

---

## 📋 Integration Checklist

Quick verification checklist:

```bash
# ✓ Service is healthy
curl -f http://localhost:8004/api/v1/health

# ✓ Metrics endpoint works
curl -f http://localhost:8004/metrics | head -10

# ✓ Trace ID in response
curl -D - http://localhost:8004/api/v1/health | grep -i "x-trace-id"

# ✓ Service in Prometheus
curl -s http://localhost:9091/api/v1/targets | \
  jq '.data.activeTargets[] | select(.labels.container_name=="image-processor-api")'

# ✓ Logs in Loki
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={container_name="image-processor-api"}' \
  --data-urlencode "start=$(date -u -d '5 minutes ago' +%s)000000000" \
  --data-urlencode "end=$(date -u +%s)000000000" | \
  jq '.data.result[0].values[0][1]'

# ✓ Docker labels correct
docker inspect image-processor-api | jq '.[].Config.Labels'

# ✓ On correct network
docker inspect image-processor-api | \
  jq '.[].NetworkSettings.Networks["activity-observability"]'

# ✓ JSON logs
docker logs image-processor-api 2>&1 | tail -1 | jq .
```

---

## 📚 Additional Resources

- **Full Documentation:** `OBSERVABILITY_INTEGRATION.md`
- **Verification Script:** `./verify-observability.sh`
- **Architecture Docs:** `/mnt/d/activity/observability-stack/ARCHITECTURE.md`
- **Prometheus Docs:** https://prometheus.io/docs/
- **Loki Docs:** https://grafana.com/docs/loki/
- **Grafana Docs:** https://grafana.com/docs/grafana/

---

**Quick Reference Version:** 1.0.0
**Last Updated:** 2025-11-10
