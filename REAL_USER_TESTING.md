# Real User Integration Testing

Complete guide for running `test_ultimate.sh` with real authentication from auth-api.

## Overview

The `test_ultimate.sh` script now performs **full end-to-end integration testing** with:
- ✅ Real user creation in auth-api (register → verify → login)
- ✅ Real JWT tokens from auth-api
- ✅ Authorization system validation (user buckets)
- ✅ Complete authentication flow testing
- ✅ 50+ comprehensive tests

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    TEST FLOW                            │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  1. scripts/create_test_user_with_token.sh             │
│     ├─ POST /api/auth/register                         │
│     ├─ GET verify code from Redis                      │
│     ├─ POST /api/auth/verify-code                      │
│     └─ POST /api/auth/login → JWT token                │
│                                                         │
│  2. test_ultimate.sh                                    │
│     ├─ Uses real JWT token                             │
│     ├─ Uploads to users/{user_id}/ bucket              │
│     ├─ Authorization auto-allows (user owns bucket)    │
│     └─ Tests complete processing pipeline              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Prerequisites

### 1. Start Infrastructure Services

```bash
cd /mnt/d/activity
./scripts/start-infra.sh  # PostgreSQL, Redis, MailHog
```

### 2. Start Auth-API

```bash
cd /mnt/d/activity/auth-api
docker compose up -d
docker logs -f auth-api  # Verify running

# Verify health
curl http://localhost:8000/health
```

### 3. Start Image-API

```bash
cd /mnt/d/activity/image-api
docker compose up -d
docker logs -f image-processor-api  # Verify running

# Verify health
curl http://localhost:8004/api/v1/health
```

## Running Tests

### Quick Start

```bash
cd /mnt/d/activity/image-api
./test_ultimate.sh
```

### What Happens

1. **User Creation** (automatic):
   ```
   [INFO] Creating real authenticated user via auth-api...
   [INFO] Step 1/4: Registering user...
   [SUCCESS] User registered, verification_token: ...
   [INFO] Step 2/4: Retrieving verification code from Redis...
   [SUCCESS] Verification code retrieved: 123456
   [INFO] Step 3/4: Verifying email...
   [SUCCESS] Email verified successfully
   [INFO] Step 4/4: Logging in to get JWT token...
   [SUCCESS] Login successful!
   [SUCCESS] User ID: 019a9182-8c3c-7744-9168-ea6f5a290ba8
   [SUCCESS] Email: test-user-1731929384@example.com
   [SUCCESS] Access Token: eyJhbGciOiJIUzI1NiIsInR5cCI...
   ```

2. **Test Execution** (10 suites, 50+ tests):
   - Suite 1: Infrastructure (7 tests)
   - Suite 2: Authentication (8 tests) **← NOW WITH REAL AUTH!**
   - Suite 3: Rate Limiting (4 tests)
   - Suite 4: Upload Validation (7 tests)
   - Suite 5: Processing Pipeline (8 tests)
   - Suite 6: Job Status (4 tests)
   - Suite 7: Image Retrieval (4 tests)
   - Suite 8: Error Handling (3 tests)
   - Suite 9: Monitoring (4 tests)
   - Suite 10: Performance (3 tests)

3. **Summary Report**:
   ```
   ╔═══════════════════════════════════════════════════════════╗
   ║                                                           ║
   ║  🎉 ALL 52 TESTS PASSED! 100% CONFIDENCE                 ║
   ║                                                           ║
   ╚═══════════════════════════════════════════════════════════╝

   📊 Performance Metrics:
     • Total execution time: 45s
     • Tests passed: 52/52 (100%)
     • Average processing time: 3s

   🔧 Service Status:
     • API: Up 2 minutes (healthy)
     • Worker: Up 2 minutes (healthy)
     • Redis: Up 2 minutes (healthy)
     • Flower: Up 2 minutes (healthy)
   ```

## Key Features

### Real Authentication Tests

The authentication suite now includes:

```bash
# Test 1: Real JWT with user bucket accepted
✅ PASS: Real JWT with user bucket accepted

# Test 2-6: Security tests (same as before)
✅ PASS: Invalid JWT rejected (401)
✅ PASS: Expired JWT rejected (401)
✅ PASS: Missing token rejected (403)
✅ PASS: Malformed token rejected
✅ PASS: Wrong signature rejected

# Test 7: Authorization test (NEW!)
✅ PASS: Cannot access another user's bucket (403)

# Test 8: System bucket test (NEW!)
✅ PASS: System bucket allows authenticated users
```

### Authorization System Validation

Tests the distributed authorization system:

1. **User Buckets**: `users/{user_id}/`
   - Auto-allows when JWT user_id matches bucket user_id
   - Denies when JWT user_id doesn't match

2. **System Buckets**: `system/`
   - Auto-allows all authenticated users

3. **Group Buckets**: `groups/{group_id}/`
   - Would call auth-api for permission check
   - (Not tested in default flow - requires group setup)

### Bucket Format Examples

```bash
# User bucket (auto-allowed)
bucket="users/019a9182-8c3c-7744-9168-ea6f5a290ba8/"

# System bucket (auto-allowed for all authenticated)
bucket="system/"

# Group bucket (requires auth-api check)
bucket="groups/photographer-group-123/"
```

## Helper Script

### `scripts/create_test_user_with_token.sh`

Standalone script for creating authenticated test users:

```bash
# Run standalone
cd /mnt/d/activity/image-api
./scripts/create_test_user_with_token.sh

# Output:
════════════════════════════════════════════
  Test User Created Successfully
════════════════════════════════════════════
User ID:      019a9182-8c3c-7744-9168-ea6f5a290ba8
Email:        test-user-1731929384@example.com
Password:     TestP@ssw0rd2024Secure!
Access Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

Use these credentials for testing:
  export TEST_USER_ID='019a9182-8c3c-7744-9168-ea6f5a290ba8'
  export TEST_ACCESS_TOKEN='eyJhbGciOiJIUzI1NiIsInR5cCI...'
════════════════════════════════════════════
```

### Use in Other Scripts

```bash
#!/bin/bash

# Source the helper (creates user automatically)
source ./scripts/create_test_user_with_token.sh

# Now use the credentials
curl -H "Authorization: Bearer $TEST_ACCESS_TOKEN" \
  -F "file=@test.jpg" \
  -F "bucket=users/$TEST_USER_ID/" \
  http://localhost:8004/api/v1/images/upload
```

## Troubleshooting

### Error: "Failed to create real user"

**Symptom**: Script exits with "Failed to create real user - tests may fail"

**Causes & Solutions**:

1. **Auth-API not running**
   ```bash
   cd /mnt/d/activity/auth-api
   docker compose up -d
   ```

2. **PostgreSQL not running**
   ```bash
   cd /mnt/d/activity
   ./scripts/start-infra.sh
   ```

3. **Redis not accessible**
   ```bash
   docker exec activity-redis redis-cli PING
   # Should return: PONG
   ```

4. **Network issues**
   ```bash
   # Check network exists
   docker network ls | grep activity-network

   # Recreate if missing
   docker network create activity-network
   ```

### Error: "Could not retrieve verification code from Redis"

**Symptom**: Step 2/4 fails to get verification code

**Solution**: Check Redis container name

```bash
# Script tries these containers in order:
# 1. auth-api (if running)
# 2. activity-redis (infrastructure)
# 3. local Redis

# Verify which is running:
docker ps --filter "name=redis"

# If using different container name, update helper script
```

### Error: "Authorization: Bearer not recognized"

**Symptom**: 401 errors despite valid token

**Cause**: JWT_SECRET mismatch between services

**Solution**: Verify matching secrets

```bash
# Auth-API secret
cat /mnt/d/activity/auth-api/.env | grep JWT_SECRET

# Image-API secret
cat /mnt/d/activity/image-api/.env | grep JWT_SECRET

# MUST BE IDENTICAL!
```

### Error: "403 Forbidden" on user bucket

**Symptom**: Upload to `users/{user_id}/` returns 403

**Cause**: user_id in bucket doesn't match JWT token

**Solution**: Ensure bucket uses exact user_id from token

```bash
# Extract user_id from token
python3 -c "
import jwt
token = '$TEST_ACCESS_TOKEN'
decoded = jwt.decode(token, options={'verify_signature': False})
print('User ID:', decoded['sub'])
"

# Use this exact ID in bucket
bucket="users/{exact-user-id-from-token}/"
```

## Advanced Testing

### Test with Group Buckets

To test group-based authorization (requires additional setup):

```bash
# 1. Create organization
curl -X POST http://localhost:8000/api/auth/organizations \
  -H "Authorization: Bearer $TEST_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Org", "slug": "test-org"}'

# 2. Create group
curl -X POST http://localhost:8000/api/auth/organizations/$ORG_ID/groups \
  -H "Authorization: Bearer $TEST_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Photographers", "description": "Photo upload group"}'

# 3. Add user to group
curl -X POST http://localhost:8000/api/auth/groups/$GROUP_ID/members \
  -H "Authorization: Bearer $TEST_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "'$TEST_USER_ID'"}'

# 4. Grant permission
curl -X POST http://localhost:8000/api/auth/groups/$GROUP_ID/permissions \
  -H "Authorization: Bearer $TEST_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"permission_id": "image:upload:group:'$GROUP_ID'"}'

# 5. Upload to group bucket
curl -H "Authorization: Bearer $TEST_ACCESS_TOKEN" \
  -F "file=@test.jpg" \
  -F "bucket=groups/$GROUP_ID/" \
  http://localhost:8004/api/v1/images/upload
```

## Comparison: Before vs After

### Before (Fake Tokens)

```bash
# Generated fake JWT with Python
TOKEN=$(python3 -c "import jwt; print(jwt.encode({'sub': 'test-user'}, 'dev-secret', algorithm='HS256'))")

# No real auth-api integration
# No real user in database
# No authorization validation
# Just JWT signature check
```

### After (Real Tokens)

```bash
# Real user creation in auth-api
source ./scripts/create_test_user_with_token.sh

# Real JWT from auth-api login
# Real user in PostgreSQL database
# Full authorization system validation
# Tests complete auth flow
```

## Benefits

1. **True Integration Testing**: Tests actual auth-api ↔ image-api integration
2. **Authorization Validation**: Verifies distributed authorization system works
3. **Real Database State**: User exists in PostgreSQL, tokens in Redis
4. **Production-Like**: Matches actual production authentication flow
5. **Reusable**: Helper script can be used in other test suites
6. **Comprehensive**: Tests 8 authentication scenarios including authorization

## Next Steps

### Optional: Test with Group Authorization

1. Create organizations, groups, and permissions in auth-api
2. Modify test suite to test `groups/{group_id}/` buckets
3. Verify auth-api authorization endpoint calls work

### Optional: Test Token Refresh

```bash
# Get refresh token from login
REFRESH_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.refresh_token')

# Refresh access token
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "'$REFRESH_TOKEN'"}'
```

### Optional: Performance Testing

```bash
# Load test with real users
for i in {1..10}; do
  source ./scripts/create_test_user_with_token.sh
  # Run upload tests with this user
done
```

## Summary

The enhanced test suite provides **production-grade integration testing** with:

✅ Real user authentication flow
✅ Real JWT tokens from auth-api
✅ Authorization system validation
✅ User bucket auto-allow testing
✅ System bucket testing
✅ Cross-service integration
✅ Comprehensive security testing
✅ 100% operational confidence

Run `./test_ultimate.sh` to experience the complete integration testing flow!
