# Technical Dashboard - Comprehensive Monitoring & Troubleshooting

## Overview

The Image Processor service now includes a **comprehensive technical dashboard** designed specifically for system monitoring, maintenance, and troubleshooting. This dashboard provides real-time visibility into all aspects of the service with auto-refresh capabilities.

## Access

- **Dashboard UI**: `http://localhost:8000/dashboard`
- **Dashboard API**: `http://localhost:8000/dashboard/data`

The dashboard is also linked from the root endpoint (`http://localhost:8000/`).

## Features

### Auto-Refresh
- **5-second auto-refresh** with countdown indicator
- Real-time monitoring without manual intervention
- Loading indicator during data fetch

### Comprehensive Metrics

#### 1. System Resources
Monitors host system performance:
- **CPU Usage**: Current CPU utilization and core count
- **Memory Usage**: RAM consumption with visual progress bar
  - Total, Used, Available memory in GB
  - Percentage utilization
- **Disk Usage**: Root filesystem statistics
  - Total, Used, Free space in GB
  - Percentage utilization
  - Visual progress bar
- **Process Metrics**: API process-specific metrics
  - RSS (Resident Set Size) memory
  - VMS (Virtual Memory Size)
  - Active thread count

**Troubleshooting Use Cases:**
- High CPU → Check for stuck processing jobs or runaway workers
- High memory → Look for memory leaks, check worker count
- High disk → Storage cleanup needed, check old images
- Thread count anomalies → Potential deadlocks or connection leaks

#### 2. Database Health
Complete SQLite database monitoring:
- **Connection Status**: Healthy/Degraded/Down
- **Database Size**: Current .db file size in MB
- **Table Counts**:
  - processing_jobs (total job records)
  - image_upload_events (audit trail entries)
  - upload_rate_limits (active rate limit windows)
- **Recent Activity**:
  - Last job created timestamp
  - Last event logged timestamp

**Troubleshooting Use Cases:**
- Database size growing rapidly → Check for cleanup policies
- No recent jobs → Workers may be down, check Celery
- Connection failures → File permissions or disk issues
- High table counts → Consider archival/cleanup strategy

#### 3. Redis Status
Redis message broker and cache monitoring:
- **Connection Status**: Connected/Disconnected
- **Redis Version**: Server version info
- **Memory Usage**:
  - Current memory consumption
  - Peak memory usage
- **Client Metrics**:
  - Connected clients count
  - Operations per second (instantaneous)
  - Total commands processed
- **Uptime**: Redis server uptime
- **Queue Lengths**:
  - Celery task queue depth

**Troubleshooting Use Cases:**
- Disconnected → Redis service down, check Docker
- High queue length → Workers not processing, scale up workers
- High memory → Check for memory leaks in tasks
- Low ops/sec with high queue → Worker bottleneck

#### 4. Celery Workers
Celery worker and task monitoring:
- **Worker Status**: Healthy/Degraded/Down
- **Active Workers**: Count of registered workers
- **Worker Names**: List of all active worker instances
- **Task Counts**:
  - Active tasks (currently executing)
  - Reserved tasks (claimed by workers, not yet started)
  - Scheduled tasks (future execution)
- **Registered Tasks**: List of all registered task types
- **Worker Stats**: Detailed per-worker statistics

**Troubleshooting Use Cases:**
- No active workers → Workers not running, check `docker compose ps worker`
- High reserved, low active → Workers may be stuck
- No registered tasks → Worker startup issue
- Status degraded → Some workers down, others up

#### 5. Processing Metrics
Image processing job statistics:
- **Jobs by Status**: Breakdown of all jobs
  - Pending (queued, not started)
  - Processing (actively being processed)
  - Completed (successfully finished)
  - Failed (processing failed after retries)
  - Retrying (retry in progress)
- **Performance (Last Hour)**:
  - Total jobs submitted
  - Completed job count
  - Failed job count
  - Average processing time in seconds
- **Performance (Last 24 Hours)**:
  - Same metrics as last hour
- **Recent Jobs Table**: Last 10 jobs with:
  - Job ID, Image ID
  - Status with color coding
  - Created timestamp
  - Completed timestamp
  - Processing time duration

**Troubleshooting Use Cases:**
- High pending count → Workers overwhelmed or down
- Long avg processing time → Check worker resources
- High failure rate → Check recent failures table for errors
- Jobs stuck in processing → Worker crash/hang, restart workers

#### 6. Storage Backend
Storage system monitoring (Local or S3):

**For Local Storage:**
- Backend type
- Storage path location
- Disk space metrics:
  - Total, Used, Free space in GB
  - Usage percentage with progress bar
- Total file count in storage
- Total unique images (from database)

**For S3 Storage:**
- Backend type
- AWS region
- Total unique images

**Troubleshooting Use Cases:**
- High disk usage → Cleanup old images, increase storage
- File count != image count × 4 → Missing variants, orphaned files
- Path doesn't exist → Configuration error

#### 7. Rate Limiting
Upload rate limit monitoring:
- **Max Uploads/Hour**: Configured limit per user
- **Active Windows**: Count of current rate limit windows
- **Users Near Limit**: Table of users at ≥80% of limit
  - User ID
  - Current count / Limit
  - Percentage used
  - Window start time

**Troubleshooting Use Cases:**
- Many users near limit → Consider increasing limits
- Single user hitting limit → Potential abuse, investigate
- No active windows → No recent uploads, check system

#### 8. Error Tracking
Comprehensive error and failure monitoring:
- **Error Summary**:
  - Failed jobs in last hour
  - Failed jobs in last 24 hours
  - Total failed jobs (all time)
- **Recent Failures Table**: Last 10 failed jobs
  - Job ID, Image ID
  - Full error message
  - Attempt count (retry attempts)
  - Failed timestamp

**Troubleshooting Use Cases:**
- Common error patterns → Fix systemic issues
- Single failure → Likely bad image, ignore
- Frequent failures → Check worker logs, dependencies
- Specific error types → Guide debugging (permissions, memory, etc.)

#### 9. Configuration Summary
Current service configuration (non-sensitive):
- WebP quality setting (0-100)
- Max upload size in MB
- Worker prefetch multiplier
- Max tasks per child (worker restart threshold)
- Allowed MIME types
- Image size variants (thumbnail, medium, large, original)

**Troubleshooting Use Cases:**
- Verify configuration matches expectations
- Compare staging vs production settings
- Understand system limits

## Dashboard Layout

The dashboard uses a **responsive grid layout** with:
- **Dark theme** optimized for terminals and low-light environments
- **Monospace font** (Consolas/Monaco) for technical readability
- **Color-coded status indicators**:
  - 🟢 Green: Healthy/Completed
  - 🟠 Orange: Degraded/Warning
  - 🔴 Red: Down/Failed
  - 🔵 Blue: Processing/Active
  - ⚫ Gray: Pending/Unknown
- **Visual progress bars** for resource utilization
- **Hover effects** for better UX
- **Auto-scrolling** to accommodate all sections

## API Endpoint

### GET `/dashboard/data`

Returns comprehensive JSON data for all dashboard metrics.

**Response Structure:**
```json
{
  "system": { ... },
  "database": { ... },
  "redis": { ... },
  "celery": { ... },
  "processing": { ... },
  "storage": { ... },
  "rate_limits": { ... },
  "errors": { ... },
  "configuration": { ... }
}
```

**Use Cases:**
- Custom monitoring tools integration
- Prometheus/Grafana exporters
- Alerting systems
- CLI monitoring scripts
- Third-party dashboards

**Example Usage:**
```bash
# Fetch dashboard data
curl http://localhost:8000/dashboard/data | jq .

# Monitor specific metrics
curl -s http://localhost:8000/dashboard/data | jq '.celery.workers.active'

# Check error count
curl -s http://localhost:8000/dashboard/data | jq '.errors.error_summary.last_hour'

# Monitor queue length
curl -s http://localhost:8000/dashboard/data | jq '.redis.queue_lengths.celery'
```

## Common Troubleshooting Scenarios

### 1. **Images Not Processing**

Check in order:
1. **Celery Workers**: Are workers active? (`celery.workers.active > 0`)
2. **Redis Queue**: Are jobs queuing? (`redis.queue_lengths.celery`)
3. **Recent Failures**: Any error patterns? (`errors.recent_failures`)
4. **Database**: Jobs being created? (`database.recent_activity.last_job_created`)

### 2. **Slow Processing**

Investigate:
1. **Processing Metrics**: Check `processing.performance.last_hour.avg_processing_time_seconds`
2. **System Resources**: CPU/Memory high? (`system.resources`)
3. **Worker Count**: Enough workers? (`celery.workers.active`)
4. **Queue Length**: Backlog building up? (`redis.queue_lengths.celery`)

### 3. **High Failure Rate**

Examine:
1. **Recent Failures**: Common error messages? (`errors.recent_failures`)
2. **Storage**: Disk full? (`storage.disk_percent_used`)
3. **Memory**: Out of memory? (`system.resources.memory.percent`)
4. **Worker Stats**: Workers restarting? (`celery.workers.stats`)

### 4. **Service Unavailable**

Verify:
1. **System Status**: API uptime (`system.uptime_human`)
2. **Database**: Connection OK? (`database.status`)
3. **Redis**: Connected? (`redis.connected`)
4. **Celery**: Workers registered? (`celery.status`)

### 5. **Rate Limit Issues**

Review:
1. **Users Near Limit**: Who's being throttled? (`rate_limits.users_near_limit`)
2. **Configuration**: Current limit? (`configuration.rate_limit_max_uploads`)
3. **Upload Events**: Recent activity? (`database.tables.upload_rate_limits`)

## Technical Details

### Dependencies
- **psutil**: System and process metrics (CPU, memory, disk)
- **redis.asyncio**: Async Redis client for connection info
- **celery.control.inspect**: Celery worker introspection
- **aiosqlite**: Async SQLite queries for database stats

### Performance
- **Data Collection**: ~200-500ms for all metrics
- **Auto-Refresh**: Every 5 seconds
- **Browser Impact**: Minimal (<1% CPU)
- **Network**: ~5-10KB per refresh (JSON data)

### Security
- **No Authentication Required**: Dashboard is read-only monitoring
- **No Sensitive Data**: JWT secrets, AWS keys excluded
- **Safe Queries**: Read-only database operations
- **Timeout Protection**: Celery inspect has 2s timeout

⚠️ **Production Recommendation**: Add authentication or restrict dashboard access to internal networks only.

## Integration Examples

### Prometheus Exporter
```python
import requests
import time

while True:
    data = requests.get('http://localhost:8000/dashboard/data').json()

    # Export metrics
    print(f'celery_active_workers {data["celery"]["workers"]["active"]}')
    print(f'processing_queue_length {data["redis"]["queue_lengths"]["celery"]}')
    print(f'failed_jobs_last_hour {data["errors"]["error_summary"]["last_hour"]}')

    time.sleep(15)
```

### Alerting Script
```bash
#!/bin/bash

# Check worker count
WORKERS=$(curl -s http://localhost:8000/dashboard/data | jq '.celery.workers.active')

if [ "$WORKERS" -eq 0 ]; then
    echo "ALERT: No active Celery workers!" | mail -s "Worker Alert" ops@example.com
fi

# Check queue length
QUEUE=$(curl -s http://localhost:8000/dashboard/data | jq '.redis.queue_lengths.celery')

if [ "$QUEUE" -gt 100 ]; then
    echo "ALERT: Queue backlog: $QUEUE tasks" | mail -s "Queue Alert" ops@example.com
fi
```

### Health Check
```bash
# Quick health check for all components
curl -s http://localhost:8000/dashboard/data | jq '{
  database: .database.status,
  redis: .redis.status,
  celery: .celery.status,
  workers: .celery.workers.active,
  queue_length: .redis.queue_lengths.celery,
  errors_last_hour: .errors.error_summary.last_hour
}'
```

## Future Enhancements

Potential additions:
- [ ] Grafana/Prometheus native integration
- [ ] Custom alert threshold configuration
- [ ] Historical metrics (time-series graphs)
- [ ] Export metrics to CSV/JSON
- [ ] WebSocket for real-time updates (no polling)
- [ ] Mobile-responsive layout
- [ ] Dark/light theme toggle
- [ ] Filtering and search for jobs/errors
- [ ] Image processing heatmap by hour
- [ ] Worker performance comparison

## Support

For issues or feature requests related to the dashboard:
1. Check Docker logs: `docker compose logs api`
2. Verify Redis: `docker compose ps redis`
3. Check workers: `docker compose ps worker`
4. Access Flower UI: `http://localhost:5555`
5. Review failed jobs in dashboard

---

**Built with ❤️ for operational excellence and rapid troubleshooting**
