# Authorization System Test Suite

Comprehensive test suite for the distributed authorization cache system.

## Test Structure

```
tests/
├── conftest.py                        # Pytest fixtures and configuration
├── test_authorization_cache.py        # Unit tests for Redis cache layer (19 tests)
├── test_circuit_breaker.py            # Unit tests for circuit breaker (15 tests)
├── test_authorization_integration.py  # Integration tests for end-to-end flows (15 tests)
├── mock_auth_api.py                   # Mock Auth-API server for manual testing
└── README.md                          # This file
```

## Prerequisites

1. **Python Dependencies**:
   ```bash
   pip install pytest pytest-asyncio redis httpx pyjwt
   # Or install all requirements:
   pip install -r requirements.txt
   ```

2. **Redis Running**:
   ```bash
   # Option 1: Start Redis with Docker Compose (recommended)
   docker compose up -d redis

   # Option 2: Start Redis standalone
   docker run -d -p 6379:6379 redis:7-alpine

   # Verify Redis is running
   redis-cli ping  # Should return PONG
   ```

3. **Environment Variables**:
   ```bash
   # Use defaults from .env or set manually
   export REDIS_URL=redis://localhost:6379/0
   export AUTH_API_URL=http://localhost:8001
   export CIRCUIT_BREAKER_THRESHOLD=5
   export CIRCUIT_BREAKER_TIMEOUT=60
   ```

## Running Tests

### Quick Test (Unit Tests Only)

```bash
# Run all unit tests
pytest tests/ -v

# Run specific test file
pytest tests/test_authorization_cache.py -v
pytest tests/test_circuit_breaker.py -v

# Run specific test
pytest tests/test_authorization_cache.py::TestAuthorizationCache::test_cache_set_and_get_allowed -v
```

### Integration Tests

```bash
# Start Mock Auth-API (in separate terminal)
python tests/mock_auth_api.py

# Run integration tests
pytest tests/test_authorization_integration.py -v
```

### Full Authorization Test Suite

```bash
# Ensure services are running
docker compose up -d redis api

# Run comprehensive test script
./test_authorization.sh

# Expected output:
# ✓ Service health checks (4 tests)
# ✓ Unit tests (50+ tests)
# ✓ API endpoint tests (4 tests)
# ✓ Cache behavior tests (2 tests)
# ✓ Circuit breaker tests (2 tests)
```

## Test Coverage

### Authorization Cache Tests (`test_authorization_cache.py`)

- ✅ Cache set and get (allowed/denied)
- ✅ Cache miss returns None
- ✅ Key isolation (org, user, permission)
- ✅ TTL expiration
- ✅ Cache invalidation (delete, invalidate user)
- ✅ TTL stratification (read/write/admin/denied)
- ✅ Cache key format validation
- ✅ Concurrent cache operations

**Total**: 19 tests

### Circuit Breaker Tests (`test_circuit_breaker.py`)

- ✅ Initial state (closed)
- ✅ Record success/failure
- ✅ State transitions (closed → open → half-open → closed)
- ✅ Threshold-based opening
- ✅ Timeout-based recovery
- ✅ Failure count tracking
- ✅ State persistence across instances
- ✅ Concurrent operations

**Total**: 15 tests

### Integration Tests (`test_authorization_integration.py`)

- ✅ End-to-end permission checks
- ✅ Cache hit/miss flows
- ✅ Auth-API integration
- ✅ Negative caching (denied permissions)
- ✅ Cache enabled/disabled modes
- ✅ Circuit breaker fail-open/fail-closed
- ✅ Organization isolation
- ✅ User cache invalidation
- ✅ AuthAPIClient (success/denied/timeout/connection error)

**Total**: 15 tests

## Mock Auth-API Server

The `mock_auth_api.py` provides a test Auth-API server with pre-configured users:

```bash
# Start mock server
python tests/mock_auth_api.py

# Access mock API
curl http://localhost:8001/health
curl http://localhost:8001/admin/debug
```

### Pre-configured Test Users

| User ID | Org ID | Permissions |
|---------|--------|-------------|
| test-user-123 | test-org-456 | image:read, image:upload, image:delete |
| admin-user-789 | test-org-456 | All permissions + admin |
| readonly-user-999 | test-org-456 | image:read only |

### Mock API Endpoints

- `POST /api/v1/authorization/check` - Permission check (main endpoint)
- `GET /health` - Health check
- `POST /admin/users` - Add test user with permissions
- `DELETE /admin/users/{org_id}/{user_id}` - Remove user
- `GET /admin/users/{org_id}/{user_id}` - Get user permissions
- `GET /admin/debug` - View all users and permissions

### Example Usage

```bash
# Check permission
curl -X POST http://localhost:8001/api/v1/authorization/check \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user-123",
    "org_id": "test-org-456",
    "permission": "image:upload"
  }'

# Response: {"allowed": true, "reason": "Direct permission granted"}

# Add custom test user
curl -X POST http://localhost:8001/admin/users \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "custom-user",
    "org_id": "custom-org",
    "permissions": ["image:read", "image:upload"]
  }'
```

## Test Configuration

### Environment Variables

Tests read configuration from environment or `.env` file:

```bash
# Redis
REDIS_URL=redis://localhost:6379/0

# Auth-API
AUTH_API_URL=http://localhost:8001
AUTH_API_TIMEOUT=5

# Circuit Breaker
CIRCUIT_BREAKER_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=60

# Cache TTLs (seconds)
AUTH_CACHE_TTL_READ=300
AUTH_CACHE_TTL_WRITE=60
AUTH_CACHE_TTL_ADMIN=30
AUTH_CACHE_TTL_DENIED=120

# Cache behavior
AUTH_CACHE_ENABLED=true
AUTH_FAIL_OPEN=false
```

### Pytest Configuration

Add `pytest.ini` in project root:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

## Troubleshooting

### Redis Connection Errors

```bash
# Error: Could not connect to Redis at 127.0.0.1:6379
# Solution: Start Redis
docker compose up -d redis

# Or use standalone Redis
docker run -d -p 6379:6379 redis:7-alpine
```

### Import Errors

```bash
# Error: ModuleNotFoundError: No module named 'app'
# Solution: Run tests from project root
cd /path/to/image-api
pytest tests/

# Or set PYTHONPATH
export PYTHONPATH=/path/to/image-api:$PYTHONPATH
pytest tests/
```

### Async Fixture Warnings

```bash
# Warning: async fixture 'redis_client' with no plugin
# Solution: Ensure pytest-asyncio is installed
pip install pytest-asyncio

# Check version
pytest --version  # Should show pytest-asyncio plugin
```

### Tests Hanging

```bash
# Issue: Tests hang during execution
# Common causes:
# 1. Redis not running (tests timeout waiting for connection)
# 2. Auth-API mock not started (integration tests fail)
# 3. Event loop not closed properly

# Solution: Use timeout
pytest tests/ -v --timeout=30
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Authorization Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio

      - name: Run authorization tests
        run: pytest tests/ -v --tb=short
        env:
          REDIS_URL: redis://localhost:6379/0
```

## Performance Benchmarks

Expected test execution times:

- **Unit tests**: ~2-5 seconds
- **Integration tests**: ~5-10 seconds (with mock API)
- **Full test suite**: ~10-15 seconds

## Contributing

When adding new authorization tests:

1. Use descriptive test names: `test_feature_scenario_expected_result`
2. Add docstrings explaining what the test validates
3. Use fixtures from `conftest.py` for shared setup
4. Clean up test data in fixtures (already handled)
5. Group related tests in classes
6. Mark slow tests: `@pytest.mark.slow`

## See Also

- [Authorization Setup Guide](../AUTHORIZATION_SETUP.md) - Complete system documentation
- [CLAUDE.md](../CLAUDE.md) - Project development guide
- [Test Scripts](../test_authorization.sh) - Comprehensive test runner
