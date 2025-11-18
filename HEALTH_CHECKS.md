# Health Check Implementation Guide

**Last Updated**: 2025-11-14
**Status**: Production-Ready
**Author**: DevOps Team

## Overview

This document describes the production-grade health check implementation for the image-api microservice. All containers now have service-specific health checks that accurately monitor their operational status.

## Problem Statement

### Original Issue
All containers (api, worker, flower) were built from a single Dockerfile with a generic health check:
```dockerfile
HEALTHCHECK CMD curl -f http://localhost:8000/api/v1/health || exit 1
```

This caused **unhealthy status for worker and flower** containers because:
- **Worker**: Runs Celery worker process (no web server)
- **Flower**: Runs on port 5555 (not 8000)
- **API**: Works correctly on port 8000 ✅

### Root Cause
- Health check defined in Dockerfile applies to ALL containers built from that image
- Each service has different operational characteristics requiring specific health checks

## Solution Architecture

### 1. Dockerfile Changes

**Before** (`Dockerfile:45-46`):
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1
```

**After** (`Dockerfile:44-45`):
```dockerfile
# NOTE: Health checks are defined per-service in docker-compose.yml
# This ensures each service (api, worker, flower) has appropriate health checks
```

**Rationale**: Remove generic health check from Dockerfile and define service-specific checks in docker-compose.yml.

### 2. Service-Specific Health Checks

#### API Service (FastAPI HTTP Server)
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

**How it works**:
- Calls FastAPI `/api/v1/health` endpoint
- Returns HTTP 200 if database, Redis, storage are accessible
- Returns HTTP 503 if any critical dependency fails

**Success criteria**: HTTP response code 200-399

#### Worker Service (Celery Worker)
```yaml
healthcheck:
  test: ["CMD-SHELL", "celery -A app.tasks.celery_app inspect ping -d celery@$$HOSTNAME -t 10 || exit 1"]
  interval: 30s
  timeout: 15s
  retries: 3
  start_period: 60s
```

**How it works**:
- Uses `celery inspect ping` to verify worker is registered with broker
- Targets specific worker using `celery@$$HOSTNAME` (double $$ for docker-compose escaping)
- Timeout of 10 seconds for Redis communication

**Success criteria**: Worker responds to ping command

**Why longer start_period (60s)?**
- Workers need time to:
  1. Connect to Redis broker (5-10s)
  2. Register with broker (5-10s)
  3. Initialize task modules (10-20s)
  4. Become ready for ping inspection (10-15s)

#### Flower Service (Celery Monitoring UI)
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:5555/healthcheck"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

**How it works**:
- Calls Flower's built-in `/healthcheck` endpoint
- Verifies web UI is responding

**Success criteria**: HTTP response code 200-399

**Security Enhancement**: Flower now requires basic authentication:
```yaml
command: celery -A app.tasks.celery_app flower --port=5555 --basic-auth=${FLOWER_USER}:${FLOWER_PASSWORD}
environment:
  FLOWER_BASIC_AUTH: ${FLOWER_USER}:${FLOWER_PASSWORD}
```

### 3. Celery Configuration Improvements

Enhanced Celery resilience with production-grade settings (`app/tasks/celery_app.py`):

```python
celery_app.conf.update(
    # Connection resilience (Celery 6.0+ best practice)
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,

    # Health check support
    worker_send_task_events=True,
    task_send_sent_event=True,
)
```

**Benefits**:
- `broker_connection_retry_on_startup=True`: Eliminates CPendingDeprecationWarning
- `broker_connection_retry=True`: Auto-reconnect on connection loss
- `broker_connection_max_retries=10`: Configurable retry limit
- `worker_send_task_events=True`: Enables Flower real-time monitoring
- `task_send_sent_event=True`: Track task lifecycle events

## Health Check Parameters Explained

| Parameter | API | Worker | Flower | Purpose |
|-----------|-----|--------|--------|---------|
| **interval** | 30s | 30s | 30s | Time between health checks |
| **timeout** | 10s | 15s | 10s | Max time for check to complete |
| **retries** | 3 | 3 | 3 | Failed attempts before unhealthy |
| **start_period** | 40s | 60s | 30s | Grace period during startup |

### Why Different Timeouts?

- **API (10s)**: HTTP endpoint should respond quickly (<1s normally)
- **Worker (15s)**: Celery inspect needs to communicate with Redis and broker
- **Flower (10s)**: Web UI should respond quickly

### Why Different Start Periods?

- **API (40s)**: FastAPI + database initialization + dependency checks
- **Worker (60s)**: Redis connection + broker registration + task module loading
- **Flower (30s)**: Web UI initialization (fastest startup)

## Security Enhancements

### Flower Authentication

**Configuration** (`.env`):
```bash
FLOWER_USER=admin
FLOWER_PASSWORD=change_in_production_secure_password_min_16_chars
```

**Production Deployment Checklist**:
- [ ] Change `FLOWER_USER` to non-default username
- [ ] Generate strong password (min 16 characters, alphanumeric + special chars)
- [ ] Consider using secret management (AWS Secrets Manager, HashiCorp Vault)
- [ ] Enable HTTPS termination for Flower (nginx/Caddy reverse proxy)

## Verification Commands

### Check Container Health Status
```bash
docker ps --filter "name=image-processor" --format "table {{.Names}}\t{{.Status}}"
```

**Expected output**:
```
NAMES                    STATUS
image-processor-api      Up X minutes (healthy)
image-processor-worker   Up X minutes (healthy)
image-processor-flower   Up X minutes (healthy)
image-processor-redis    Up X minutes (healthy)
```

### Test API Health Endpoint
```bash
curl -f http://localhost:8009/api/v1/health
```

**Expected**: HTTP 200 with JSON health status

### Test Flower UI (with authentication)
```bash
curl -u admin:your_password http://localhost:5555/healthcheck
```

**Expected**: `OK` response

### Test Celery Worker Directly
```bash
docker exec image-processor-worker celery -A app.tasks.celery_app inspect ping -t 5
```

**Expected**:
```json
{
  "celery@container_id": {
    "ok": "pong"
  }
}
```

### View Detailed Health Check Logs
```bash
docker inspect image-processor-worker --format='{{json .State.Health}}' | python3 -m json.tool
```

**Key fields**:
- `Status`: `healthy` | `unhealthy` | `starting`
- `FailingStreak`: Number of consecutive failed checks
- `Log`: Array of recent health check results with timestamps

## Troubleshooting

### Worker Shows "unhealthy"

**Check 1**: Verify worker is registered with broker
```bash
docker exec image-processor-worker celery -A app.tasks.celery_app inspect active
```

**Check 2**: Examine worker logs for connection errors
```bash
docker logs image-processor-worker --tail 50 | grep -E "ERROR|WARNING|Connection"
```

**Check 3**: Verify Redis connectivity
```bash
docker exec image-processor-worker python3 -c "import redis; r = redis.from_url('redis://redis:6379/0'); print(r.ping())"
```

**Common causes**:
- Redis connection issues → Check `docker ps | grep redis`
- Broker authentication mismatch → Verify `REDIS_URL` in .env
- Startup still in progress → Wait for `start_period` to elapse
- Task import errors → Check `docker logs image-processor-worker` for Python exceptions

### Flower Shows "unhealthy"

**Check 1**: Verify Flower web UI is responding
```bash
curl -f http://localhost:5555/healthcheck
```

**Check 2**: Check Flower logs
```bash
docker logs image-processor-flower --tail 30
```

**Common causes**:
- Port conflict on 5555 → Check `netstat -tuln | grep 5555`
- Authentication misconfiguration → Verify `FLOWER_USER` and `FLOWER_PASSWORD` match
- Redis connection issues → Same as worker troubleshooting

### API Shows "unhealthy"

**Check 1**: Test health endpoint directly
```bash
docker exec image-processor-api curl -f http://localhost:8000/api/v1/health
```

**Check 2**: Check API logs for startup errors
```bash
docker logs image-processor-api --tail 50 | grep -E "ERROR|CRITICAL|Exception"
```

**Common causes**:
- Database initialization failed → Check SQLite permissions on `/data/processor.db`
- Redis connection failed → Verify `REDIS_URL` configuration
- Missing environment variables → Review `.env` file

## Best Practices

### 1. Health Check Design Principles

✅ **DO**:
- Define service-specific health checks in docker-compose.yml
- Use appropriate timeouts for each service type
- Include grace period (start_period) for slow-starting services
- Test critical dependencies (database, Redis, storage)
- Return different HTTP codes for different failure types (503 for degraded)

❌ **DON'T**:
- Use generic health checks in Dockerfile for multi-service images
- Set timeout longer than interval (causes overlapping checks)
- Make health checks too complex (should complete in <1s normally)
- Test non-critical features in health checks
- Return 200 if service can't process requests

### 2. Monitoring Integration

**Prometheus Metrics** (via `/metrics` endpoint):
```yaml
# Container health status
container_health_status{service="image-processor-api"} 1  # 1=healthy, 0=unhealthy

# Health check execution time
health_check_duration_seconds{service="image-processor-api"} 0.045
```

**Loki Log Queries** (structured logs):
```logql
# All health check failures
{service_name="image-processor-worker"} |= "health check failed"

# Health check duration trending
{service_name="image-processor-api"} | json | duration_ms > 100
```

**Grafana Alerts**:
- Alert when `container_health_status` = 0 for >2 minutes
- Alert when health check duration >1s (performance degradation)
- Alert when `FailingStreak` > 5 (repeated failures)

### 3. Production Deployment

**Pre-deployment Checklist**:
- [ ] Change Flower credentials from defaults
- [ ] Adjust health check intervals based on load (consider 60s for high-traffic)
- [ ] Configure alerting for unhealthy containers
- [ ] Test health checks under load (use load testing tools)
- [ ] Document custom health check endpoints in API docs
- [ ] Set up health check dashboards in Grafana

**Container Orchestration**:
```yaml
# Kubernetes example
livenessProbe:
  httpGet:
    path: /api/v1/health
    port: 8000
  initialDelaySeconds: 40
  periodSeconds: 30
  timeoutSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /api/v1/ready
    port: 8000
  initialDelaySeconds: 20
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 2
```

## Migration Notes

### Changes Made (2025-11-14)

1. **Dockerfile**: Removed generic `HEALTHCHECK` directive
2. **docker-compose.yml**: Added service-specific health checks for worker and flower
3. **app/tasks/celery_app.py**: Added broker connection resilience settings
4. **.env**: Added `FLOWER_USER` and `FLOWER_PASSWORD` for security

### Rebuild Required

After these changes, containers **MUST** be rebuilt:
```bash
cd /mnt/d/activity/image-api
docker compose down
docker compose build --no-cache
docker compose up -d
```

**Why `--no-cache`?**
- Ensures new Dockerfile is used (without old HEALTHCHECK)
- Forces pip to reinstall dependencies with new Celery settings
- Clears any cached layers with old configuration

### Backward Compatibility

✅ **Compatible with**:
- Existing `.env` configuration (new fields have defaults)
- Current API contracts (no endpoint changes)
- Monitoring systems (same `/metrics` endpoint)
- Log aggregation (same structured log format)

⚠️ **Breaking changes**:
- Flower now requires authentication (HTTP 401 without credentials)
- Health check endpoints changed for worker/flower (monitoring updates needed)

## References

- [Celery Health Checks](https://docs.celeryproject.org/en/stable/userguide/monitoring.html)
- [Docker Health Check Best Practices](https://docs.docker.com/engine/reference/builder/#healthcheck)
- [Flower Documentation](https://flower.readthedocs.io/)
- [FastAPI Health Checks](https://fastapi.tiangolo.com/advanced/health-checks/)

## Support

For issues or questions:
1. Check logs: `docker logs <container-name> --tail 50`
2. Verify configuration: `.env` file and `docker-compose.yml`
3. Review this documentation
4. Contact DevOps team

---

**Document Version**: 1.0
**Last Verified**: 2025-11-14
**Next Review**: 2025-12-14
