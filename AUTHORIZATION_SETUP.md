# Distributed Authorization System - Setup Guide

## Overview

The image-api now includes a **distributed authorization cache system** that enables permission-based access control without bloating JWT tokens with group memberships. This document explains the architecture, setup, and migration process.

## 🎯 Problem Statement

**Challenge**: You have an auth-api managing user group memberships, but you don't want to include 100+ groups in JWT tokens.

**Solution**: JWT tokens remain minimal (only `user_id`, `org_id`, basic claims). Authorization happens via auth-api with intelligent Redis caching.

## 🏗️ Architecture

### Flow Diagram

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ JWT (user_id, org_id)
       ▼
┌─────────────────────────────────────────┐
│          Image API Endpoint             │
│  require_permission("image:upload")     │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│     Authorization Service               │
│  1. Check Redis Cache (fast path)      │
│  2. If miss → Query Auth-API            │
│  3. Cache result with TTL               │
│  4. Return decision                     │
└──────┬──────────────────────────────────┘
       │
       ├──────────────┬──────────────────┐
       │              │                  │
       ▼              ▼                  ▼
  ┌────────┐    ┌─────────┐      ┌──────────┐
  │ Redis  │    │Auth-API │      │ Circuit  │
  │ Cache  │    │ Check   │      │ Breaker  │
  └────────┘    └─────────┘      └──────────┘
```

### Components

1. **AuthorizationCache** - Redis-based permission caching with configurable TTL
2. **CircuitBreaker** - Protects against auth-api failures (fail-fast pattern)
3. **AuthAPIClient** - HTTP client for auth-api with circuit breaker integration
4. **AuthorizationService** - Main orchestrator with fallback logic

### Cache Key Pattern

```
auth:permission:{org_id}:{user_id}:{permission} → "1" (allowed) | "0" (denied)
```

**Example**:
```
auth:permission:acme-corp:user-123:image:upload → "1"  (TTL: 60s)
auth:permission:acme-corp:user-456:image:delete → "0"  (TTL: 120s)
```

### TTL Strategy

Different permissions have different cache durations based on sensitivity:

| Permission Type | TTL | Rationale |
|----------------|-----|-----------|
| Read operations (`image:read`) | 5 minutes | Less sensitive, optimize for performance |
| Write operations (`image:upload`) | 1 minute | More sensitive, balance security/performance |
| Admin operations (`image:admin`) | 30 seconds | Very sensitive, prioritize security |
| Denied permissions | 2 minutes | Prevent repeated unauthorized attempts |

## 🚀 Setup Instructions

### Step 1: Update JWT Tokens

Your JWT issuer (auth-api) must include `org_id` in token payload:

**Old JWT payload**:
```json
{
  "sub": "user-123",
  "email": "user@example.com",
  "exp": 1735689600
}
```

**New JWT payload** (backwards compatible):
```json
{
  "sub": "user-123",
  "org_id": "acme-corp",
  "email": "user@example.com",
  "name": "John Doe",
  "exp": 1735689600
}
```

**Note**: Old tokens without `org_id` will default to `"default-org"` during migration period.

### Step 2: Configure Environment Variables

Update your `.env` file (see `.env.example` for full configuration):

```bash
# Authorization System
AUTH_API_URL=http://auth-api:8000
AUTH_API_TIMEOUT=5
AUTH_CACHE_ENABLED=true
AUTH_FAIL_OPEN=false  # IMPORTANT: false = fail-closed (recommended)

# Circuit Breaker
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=60

# Cache TTLs (tune based on your security requirements)
AUTH_CACHE_TTL_READ=300     # 5 minutes
AUTH_CACHE_TTL_WRITE=60     # 1 minute
AUTH_CACHE_TTL_ADMIN=30     # 30 seconds
AUTH_CACHE_TTL_DENIED=120   # 2 minutes
```

### Step 3: Implement Auth-API Endpoint

Your auth-api must expose a permission check endpoint:

**Endpoint**: `POST /api/v1/authorization/check`

**Request**:
```json
{
  "org_id": "acme-corp",
  "user_id": "user-123",
  "permission": "image:upload"
}
```

**Response (200 OK - Permission granted)**:
```json
{
  "allowed": true,
  "groups": ["photographers", "editors"],  // optional context
  "cached_until": "2025-01-15T10:30:00Z"  // optional hint
}
```

**Response (403 Forbidden - Permission denied)**:
```json
{
  "allowed": false,
  "reason": "user not in required groups"
}
```

**Response (500 Internal Server Error - Auth-API error)**:
```json
{
  "error": "database connection failed"
}
```

### Step 4: Define Permission Mapping

In your auth-api, map permissions to group requirements:

```python
# Example permission mapping in auth-api
PERMISSION_GROUPS = {
    "image:upload": ["photographers", "editors", "admins"],
    "image:read": ["photographers", "editors", "admins", "viewers"],
    "image:delete": ["editors", "admins"],
    "image:admin": ["admins"]
}

async def check_permission(org_id: str, user_id: str, permission: str) -> bool:
    """Check if user has permission via group membership."""
    # 1. Get user's groups in organization
    user_groups = await db.get_user_groups(org_id, user_id)

    # 2. Get required groups for permission
    required_groups = PERMISSION_GROUPS.get(permission, [])

    # 3. Check intersection
    return bool(set(user_groups) & set(required_groups))
```

### Step 5: Restart Services

```bash
# Restart image-api to load new authorization system
docker compose restart api

# Check startup logs
docker compose logs -f api | grep authorization

# Expected output:
# authorization_service_initialized auth_api_url=http://auth-api:8000 ...
```

## 🔍 Verification

### Test 1: Health Check

```bash
curl http://localhost:8000/api/v1/health/auth | jq .
```

**Expected output**:
```json
{
  "status": "healthy",
  "auth_api": {
    "url": "http://auth-api:8000",
    "circuit_breaker": {
      "state": "closed",
      "failures": 0
    }
  },
  "cache": {
    "enabled": true,
    "redis_connection": "healthy"
  }
}
```

### Test 2: Upload with Authorization

```bash
# Generate test token (with org_id)
export TOKEN=$(python3 -c "
import jwt
print(jwt.encode(
    {'sub': 'user-123', 'org_id': 'test-org'},
    'dev-secret-change-in-production',
    algorithm='HS256'
))
")

# Test upload (requires image:upload permission)
curl -X POST http://localhost:8000/api/v1/images/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_images/test_500x500.jpg" \
  -F "bucket=test-uploads" \
  -F "metadata={\"context\":\"test\"}"
```

**First request**: Cache miss → Auth-API called → Result cached
**Second request**: Cache hit → No auth-API call (< 5ms)

### Test 3: Monitor Cache

```bash
# Connect to Redis
docker exec -it image-processor-redis redis-cli

# Check cached permissions
KEYS auth:permission:*

# Example output:
# 1) "auth:permission:test-org:user-123:image:upload"

# Check specific permission
GET auth:permission:test-org:user-123:image:upload
# Output: "1" (allowed) or "0" (denied)

# Check TTL
TTL auth:permission:test-org:user-123:image:upload
# Output: 58 (seconds remaining)
```

### Test 4: Circuit Breaker

```bash
# Simulate auth-api failure (stop auth-api)
docker compose stop auth-api

# Try upload (circuit breaker should open after 5 failures)
for i in {1..6}; do
  curl -X POST http://localhost:8000/api/v1/images/upload \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@test.jpg" \
    -F "bucket=test"
  echo "Request $i"
done

# Check circuit breaker status
curl http://localhost:8000/api/v1/health/auth | jq '.auth_api.circuit_breaker'

# Expected output after 5 failures:
# {
#   "state": "open",
#   "failures": 5
# }
```

## 📊 Monitoring

### Dashboard Integration

The authorization system is integrated into the technical dashboard:

```bash
open http://localhost:8000/dashboard
```

**Authorization Metrics** (auto-refresh):
- Circuit breaker state
- Cache hit/miss rates
- Auth-API response times
- Recent authorization failures

### Logs to Monitor

```bash
# Authorization decisions
docker compose logs -f api | grep authorization_decision

# Cache hits
docker compose logs -f api | grep auth_cache_hit

# Circuit breaker events
docker compose logs -f api | grep circuit_breaker

# Auth-API failures
docker compose logs -f api | grep auth_api_call_failed
```

### Example Log Output

```json
{
  "event": "authorization_decision",
  "org_id": "acme-corp",
  "user_id": "user-123",
  "permission": "image:upload",
  "allowed": true,
  "source": "cache",
  "duration_ms": 2.4
}
```

## 🔧 Configuration Tuning

### Security vs Performance Trade-offs

#### High Security (Short TTLs)

```bash
AUTH_CACHE_TTL_READ=60      # 1 minute
AUTH_CACHE_TTL_WRITE=30     # 30 seconds
AUTH_CACHE_TTL_ADMIN=10     # 10 seconds
AUTH_CACHE_TTL_DENIED=60    # 1 minute
```

**Impact**:
- ✅ Permission changes propagate quickly (10-60s)
- ❌ More load on auth-api
- ❌ Higher latency for cache misses

#### High Performance (Long TTLs)

```bash
AUTH_CACHE_TTL_READ=600     # 10 minutes
AUTH_CACHE_TTL_WRITE=300    # 5 minutes
AUTH_CACHE_TTL_ADMIN=60     # 1 minute
AUTH_CACHE_TTL_DENIED=300   # 5 minutes
```

**Impact**:
- ✅ Minimal auth-api load
- ✅ Low latency (most requests from cache)
- ❌ Permission changes take 1-10 minutes to propagate

### Recommended Settings by Environment

| Environment | Read | Write | Admin | Denied | Rationale |
|-------------|------|-------|-------|--------|-----------|
| Development | 60s  | 30s   | 10s   | 60s    | Quick feedback during testing |
| Staging     | 300s | 60s   | 30s   | 120s   | Balance for integration testing |
| Production  | 300s | 60s   | 30s   | 120s   | Security-first, acceptable performance |

### Circuit Breaker Tuning

```bash
# Aggressive (fail fast)
CIRCUIT_BREAKER_THRESHOLD=3  # Open after 3 failures
CIRCUIT_BREAKER_TIMEOUT=30   # Retry after 30s

# Conservative (tolerate transient issues)
CIRCUIT_BREAKER_THRESHOLD=10  # Open after 10 failures
CIRCUIT_BREAKER_TIMEOUT=120   # Retry after 2 minutes
```

### Fail-Open vs Fail-Closed

```bash
# Fail-Closed (RECOMMENDED for production)
AUTH_FAIL_OPEN=false
# → Deny access when auth-api unavailable
# → Better security, potential downtime impact

# Fail-Open (ONLY for development/testing)
AUTH_FAIL_OPEN=true
# → Allow access when auth-api unavailable
# → Better availability, security risk
```

## 🚨 Troubleshooting

### Issue: "Authorization service temporarily unavailable" (503)

**Causes**:
1. Auth-API is down
2. Redis is down
3. Circuit breaker is open

**Diagnosis**:
```bash
# Check circuit breaker
curl http://localhost:8000/api/v1/health/auth | jq '.auth_api.circuit_breaker'

# Check Redis
docker exec image-processor-redis redis-cli ping

# Check auth-api
curl http://auth-api:8000/health
```

**Solutions**:
1. If auth-api is down → Fix auth-api, circuit will close automatically after `CIRCUIT_BREAKER_TIMEOUT`
2. If Redis is down → Restart Redis: `docker compose restart redis`
3. If circuit is open → Wait for timeout or manually reset Redis key: `DEL auth:circuit_breaker:state`

### Issue: "Permission denied" (403) but user should have access

**Causes**:
1. User's group membership changed but cache not invalidated
2. Permission mapping incorrect in auth-api
3. Negative caching (previous denial is cached)

**Diagnosis**:
```bash
# Check cached permission
docker exec -it image-processor-redis redis-cli
GET auth:permission:{org_id}:{user_id}:{permission}
TTL auth:permission:{org_id}:{user_id}:{permission}

# Check auth-api directly
curl -X POST http://auth-api:8000/api/v1/authorization/check \
  -H "Content-Type: application/json" \
  -d '{"org_id":"test-org","user_id":"user-123","permission":"image:upload"}'
```

**Solutions**:
1. Invalidate user's cache: See "Cache Invalidation" section below
2. Wait for TTL to expire (max 5 minutes for read operations)
3. Verify auth-api permission mapping

### Issue: High auth-api load

**Causes**:
1. Cache disabled or TTLs too short
2. Many unique users/permissions (low cache hit rate)
3. Frequent cache invalidations

**Diagnosis**:
```bash
# Monitor auth-api request rate
docker compose logs auth-api | grep "/api/v1/authorization/check" | wc -l

# Check cache hit rates in logs
docker compose logs api | grep authorization_decision | \
  jq -s 'group_by(.source) | map({source: .[0].source, count: length})'
```

**Solutions**:
1. Increase TTLs: `AUTH_CACHE_TTL_READ=600` (10 minutes)
2. Verify cache is enabled: `AUTH_CACHE_ENABLED=true`
3. Scale auth-api horizontally if needed

### Issue: Circuit breaker keeps opening

**Causes**:
1. Auth-API is unstable or overloaded
2. Network issues between image-api and auth-api
3. Threshold too aggressive

**Solutions**:
1. Scale auth-api: Add more instances
2. Increase circuit breaker threshold: `CIRCUIT_BREAKER_THRESHOLD=10`
3. Increase auth-api timeout: `AUTH_API_TIMEOUT=10`
4. Check network latency: `docker exec api ping auth-api`

## 🔄 Cache Invalidation

### Manual Invalidation (Emergency)

```bash
# Invalidate all permissions for a user
docker exec -it image-processor-redis redis-cli

# Find all keys for user
KEYS auth:permission:acme-corp:user-123:*

# Delete all keys for user
DEL auth:permission:acme-corp:user-123:image:upload
DEL auth:permission:acme-corp:user-123:image:read
# ... or use pattern delete ...

# Delete all auth cache (nuclear option)
KEYS auth:permission:* | xargs redis-cli DEL
```

### Automated Invalidation (Recommended)

Add a webhook endpoint in auth-api that publishes to Redis pub/sub when user's group membership changes:

**In auth-api**:
```python
@router.post("/api/v1/users/{user_id}/groups")
async def update_user_groups(user_id: str, groups: List[str]):
    """Update user's group membership."""
    # Update database
    await db.update_user_groups(user_id, groups)

    # Publish cache invalidation event
    redis_client = redis.from_url(REDIS_URL)
    message = {
        "type": "invalidate_user_cache",
        "org_id": org_id,
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat()
    }
    await redis_client.publish("auth:cache:invalidation", json.dumps(message))

    return {"status": "updated"}
```

**In image-api** (future enhancement):
Add a background task that subscribes to `auth:cache:invalidation` channel and invalidates cache accordingly.

## 📈 Performance Metrics

### Expected Performance

| Metric | Value | Notes |
|--------|-------|-------|
| Cache hit authorization | < 5ms | Redis local lookup |
| Cache miss authorization | 50-200ms | Auth-API call + cache write |
| Circuit breaker check | < 1ms | Redis state lookup |
| Cache invalidation | < 10ms | Redis DELETE operations |

### Benchmark

```bash
# Run 1000 uploads with same user (cache hits)
time for i in {1..1000}; do
  curl -s -X POST http://localhost:8000/api/v1/images/upload \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@test.jpg" > /dev/null
done

# Expected: < 10s total (< 10ms per request)
```

## 🔐 Security Considerations

### ✅ Security Features

1. **Fail-closed by default** - Denies access when auth-api unavailable
2. **Organization isolation** - Cache keys include `org_id`
3. **Negative caching** - Prevents brute-force permission attempts
4. **TTL stratification** - More sensitive operations have shorter cache
5. **Audit logging** - All authorization decisions logged
6. **Circuit breaker** - Prevents cascade failures

### ⚠️ Security Warnings

1. **Never use `AUTH_FAIL_OPEN=true` in production** - This allows unauthorized access when auth-api is down
2. **Keep TTLs reasonable** - Very long TTLs (> 10 minutes) delay permission revocation
3. **Monitor failed authorizations** - High failure rates may indicate attack attempts
4. **Secure Redis** - Redis contains authorization cache, secure with authentication
5. **HTTPS for auth-api** - Communication between image-api and auth-api should be encrypted in production

### Compliance Notes

- **GDPR**: User authorization decisions are logged with timestamps (audit trail)
- **SOC 2**: Circuit breaker provides resilience, fail-closed ensures security
- **Zero Trust**: Every request is authenticated + authorized, no implicit trust

## 🎓 Permission Design Best Practices

### Naming Convention

Use hierarchical permission strings:

```
{resource}:{action}
```

**Examples**:
- `image:read` - View image metadata and URLs
- `image:upload` - Upload new images
- `image:delete` - Delete images
- `image:admin` - All image operations + administrative tasks
- `org:admin` - Organization-wide administrative access

### Permission Hierarchy (Future Enhancement)

Implement permission inheritance in auth-api:

```python
PERMISSION_HIERARCHY = {
    "image:admin": ["image:read", "image:upload", "image:delete"],
    "org:admin": ["image:admin", "user:admin"]
}

def has_permission(user_groups, required_permission):
    """Check if user has permission or a parent permission."""
    # Check direct permission
    if check_direct_permission(user_groups, required_permission):
        return True

    # Check parent permissions
    for parent, children in PERMISSION_HIERARCHY.items():
        if required_permission in children:
            if check_direct_permission(user_groups, parent):
                return True

    return False
```

## 📚 Additional Resources

- **Redis Commands**: https://redis.io/commands
- **Circuit Breaker Pattern**: https://martinfowler.com/bliki/CircuitBreaker.html
- **JWT Best Practices**: https://tools.ietf.org/html/rfc8725
- **FastAPI Dependencies**: https://fastapi.tiangolo.com/tutorial/dependencies/

## 🆘 Support

If you encounter issues not covered in this guide:

1. Check logs: `docker compose logs -f api | grep authorization`
2. Check health: `curl http://localhost:8000/api/v1/health/auth`
3. Check Redis: `docker exec image-processor-redis redis-cli INFO`
4. Review auth-api logs for permission check errors
5. Open an issue with debug logs attached

## 🎉 Success Checklist

- [ ] JWT tokens include `org_id` claim
- [ ] Auth-API implements `/api/v1/authorization/check` endpoint
- [ ] Environment variables configured in `.env`
- [ ] Services restarted successfully
- [ ] Health check shows `"status": "healthy"`
- [ ] Test upload succeeds with valid token
- [ ] Test upload fails with invalid token (403)
- [ ] Cache is working (check Redis keys)
- [ ] Circuit breaker responds to auth-api failures
- [ ] Logs show authorization decisions with source (cache/auth_api)

**Congratulations! Your distributed authorization system is operational!** 🚀
