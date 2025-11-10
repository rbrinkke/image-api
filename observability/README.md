# Image API Observability Configuration

This directory contains observability configuration for the Image API service:
- **Grafana Dashboards** - Pre-built monitoring dashboards
- **Prometheus Alerts** - Production-ready alert rules

## 📁 Structure

```
observability/
├── README.md                               # This file
├── grafana/
│   └── dashboards/
│       └── image-api-dashboard.json        # Grafana dashboard (22 panels)
└── prometheus/
    └── alerts/
        └── image-api-alerts.yml            # Alert rules (19 alerts)
```

## 🎯 Dashboard Features

The **Image API Dashboard** includes 22 panels organized in 6 sections:

### 1. Service Health Overview (5 panels)
- Service Status (UP/DOWN)
- Requests/sec
- Success Rate (%)
- Response Time (P50/P95/P99)
- Active Processing Jobs

### 2. HTTP Metrics (4 panels)
- Request Rate by Endpoint
- Response Time Distribution
- HTTP Status Codes
- Active Requests by Method

### 3. Image Processing Metrics (6 panels)
- Upload Rate
- Processing Success Rate
- Average Processing Time
- Celery Queue Length
- Processing Jobs by Status
- Processing Time by Size (thumbnail/medium/large/original)

### 4. Storage & Database Metrics (4 panels)
- Storage Operations by Type/Status
- Storage Operation Latency
- Database Query Rate
- Database Query Latency

### 5. Celery Worker Metrics (2 panels)
- Celery Task Rate by Status
- Celery Task Duration

### 6. Logs Panel (1 panel)
- Recent Logs (real-time)

## ⚠️ Alert Rules

The alert rules file contains **19 alerts** across 3 severity levels:

### CRITICAL (9 alerts)
- `ImageAPIDown` - Service unavailable
- `ImageAPICriticalErrorRate` - Error rate > 15%
- `ImageAPICriticalSlowResponses` - P95 latency > 5s
- `ImageProcessingCriticalFailureRate` - Processing failures > 25%
- `ImageProcessingCriticalSlowProcessing` - P95 processing > 30s
- `CeleryQueueCriticallySaturated` - Queue > 100 tasks
- `ImageAPIStorageOperationFailures` - Storage errors
- `ImageAPIDatabaseErrors` - Database errors
- `ImageAPIWorkerDown` - Worker unavailable

### WARNING (8 alerts)
- `ImageAPIHighErrorRate` - Error rate > 5%
- `ImageAPISlowResponses` - P95 latency > 2s
- `ImageProcessingFailureRate` - Processing failures > 10%
- `ImageProcessingSlowProcessing` - P95 processing > 10s
- `CeleryQueueSaturated` - Queue > 50 tasks
- `ImageAPIRateLimitHitsIncreasing` - Rate limiting active
- `ImageAPISlowStorageOperations` - Storage slow
- `ImageAPISlowDatabaseQueries` - Database slow

### INFO (2 alerts)
- `ImageAPIHighUploadRejectionRate` - Many uploads rejected
- `ImageAPINoUploadsReceived` - No uploads for 15m

## 🚀 Usage

### Option 1: Manual Import (Quick Start)

**Import Dashboard:**
1. Open Grafana: http://localhost:3002
2. Go to Dashboards → Import
3. Upload `grafana/dashboards/image-api-dashboard.json`
4. Select Prometheus data source
5. Click Import

**Add Alerts:**
1. Copy content from `prometheus/alerts/image-api-alerts.yml`
2. Add to your Prometheus `alerts.yml` file
3. Reload Prometheus: `curl -X POST http://localhost:9091/-/reload`

### Option 2: Automated Provisioning (Production)

**For centralized observability stack integration:**

1. **Dashboard Provisioning:**
   Copy dashboard to observability-stack:
   ```bash
   cp observability/grafana/dashboards/image-api-dashboard.json \
      /path/to/observability-stack/grafana/dashboards/
   ```

2. **Alert Provisioning:**
   Merge alerts into central alerts.yml:
   ```bash
   cat observability/prometheus/alerts/image-api-alerts.yml >> \
       /path/to/observability-stack/prometheus/alerts.yml
   ```

3. **Restart Services:**
   ```bash
   cd /path/to/observability-stack
   docker compose restart grafana prometheus
   ```

### Option 3: Docker Volume Mounts (Development)

Mount this directory into your observability stack:

```yaml
# docker-compose.yml
services:
  grafana:
    volumes:
      - ./observability/grafana/dashboards:/etc/grafana/provisioning/dashboards/image-api:ro

  prometheus:
    volumes:
      - ./observability/prometheus/alerts:/etc/prometheus/alerts.d/image-api:ro
```

## 📊 Metrics Used

The dashboard and alerts rely on metrics exposed by the Image API:

### HTTP Metrics
- `http_requests_total{exported_service="image-processor"}`
- `http_request_duration_seconds_bucket{exported_service="image-processor"}`
- `http_requests_in_progress{exported_service="image-processor"}`

### Processing Metrics
- `image_uploads_total{exported_service="image-processor"}`
- `image_processing_jobs_total{exported_service="image-processor"}`
- `image_processing_duration_seconds_bucket{exported_service="image-processor"}`
- `image_processing_jobs_active{exported_service="image-processor"}`

### Storage Metrics
- `storage_operations_total{exported_service="image-processor"}`
- `storage_operation_duration_seconds_bucket{exported_service="image-processor"}`

### Database Metrics
- `database_queries_total{exported_service="image-processor"}`
- `database_query_duration_seconds_bucket{exported_service="image-processor"}`

### Celery Metrics
- `celery_tasks_total{exported_service="image-processor"}`
- `celery_task_duration_seconds_bucket{exported_service="image-processor"}`
- `celery_queue_length{exported_service="image-processor"}`

### Rate Limiting
- `rate_limit_rejections_total{exported_service="image-processor"}`

Ensure the Image API `/metrics` endpoint is being scraped by Prometheus with these labels.

## 🔗 Prerequisites

**Required:**
- Prometheus scraping Image API metrics endpoint
- Grafana with Prometheus data source configured
- Image API exposing metrics at `/metrics` endpoint

**Labels Required:**
- `exported_service="image-processor"` (main service identifier)
- `container_name="image-processor-api"` (for availability checks)
- `container_name="image-processor-worker"` (for worker checks)

**Verify metrics are available:**
```bash
# Check if Prometheus is scraping
curl http://localhost:9091/api/v1/targets | jq '.data.activeTargets[] | select(.labels.container_name=="image-processor-api")'

# Check if metrics exist
curl http://localhost:9091/api/v1/query?query=up{container_name="image-processor-api"}
```

## 📝 Customization

### Dashboard Customization
- Time ranges: Default 1 hour, adjustable
- Refresh rate: Default 30s, adjustable
- Percentile: Default P95, variable selector for P50/P95/P99
- Thresholds: Color-coded (green/yellow/red), customizable per panel

### Alert Customization
- **Thresholds**: Adjust severity thresholds in alert expressions
- **Duration**: Adjust `for:` duration before firing
- **Labels**: Add custom labels for routing
- **Annotations**: Customize alert messages

Example threshold change:
```yaml
# Make error rate alert more sensitive
- alert: ImageAPIHighErrorRate
  expr: |
    (...) > 0.03  # Changed from 0.05 (5%) to 0.03 (3%)
  for: 2m        # Changed from 3m to 2m
```

## 🎯 Best Practices

1. **Start with Manual Import**: Test dashboards/alerts before automation
2. **Customize Thresholds**: Adjust based on your SLOs/SLAs
3. **Test Alerts**: Use `amtool` to test alert routing
4. **Monitor Alert Fatigue**: Tune thresholds to reduce noise
5. **Document Changes**: Track customizations in git
6. **Version Control**: Keep observability config with service code

## 🆘 Support

For issues or questions:
- Check the main Image API documentation
- Review Prometheus/Grafana logs
- Verify metrics endpoint accessibility
- Confirm label consistency

## 📚 Related Documentation

- Main README: `../README.md`
- Integration Summary: `../INTEGRATION_SUMMARY.md`
- Observability Integration: `../OBSERVABILITY_INTEGRATION.md`
- Quick Reference: `../OBSERVABILITY_QUICK_REFERENCE.md`
