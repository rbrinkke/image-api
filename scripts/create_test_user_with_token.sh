#!/usr/bin/env bash
#
# Create Test User with Real JWT Token
#
# This script creates a verified user in auth-api and returns a real JWT token.
# Used by test_ultimate.sh for integration testing with real authentication.
#
# Usage:
#   source ./scripts/create_test_user_with_token.sh
#   # Now you have: $TEST_USER_ID, $TEST_USER_EMAIL, $TEST_ACCESS_TOKEN
#
# Environment:
#   AUTH_API_URL: Auth API base URL (default: http://localhost:8000)
#

set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

AUTH_API_URL="${AUTH_API_URL:-http://localhost:8000}"
TEST_PASSWORD="TestP@ssw0rd2024Secure!"

# Generate unique email with timestamp
TIMESTAMP=$(date +%s)
TEST_USER_EMAIL="test-user-${TIMESTAMP}@example.com"

# Color codes (optional, for pretty output)
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# ═══════════════════════════════════════════════════════════════════════════
# MAIN USER CREATION FLOW
# ═══════════════════════════════════════════════════════════════════════════

create_test_user_with_token() {
    log_info "Creating test user in auth-api: $TEST_USER_EMAIL"

    # -----------------------------------------------------------------------
    # Step 1: Register user
    # -----------------------------------------------------------------------
    log_info "Step 1/4: Registering user..."

    REGISTER_RESPONSE=$(curl -sS -X POST "$AUTH_API_URL/api/auth/register" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$TEST_USER_EMAIL\", \"password\": \"$TEST_PASSWORD\"}")

    # Check for registration errors
    if echo "$REGISTER_RESPONSE" | grep -qi "error\|failed"; then
        log_error "Registration failed: $REGISTER_RESPONSE"
        return 1
    fi

    # Extract verification token from response
    VERIFICATION_TOKEN=$(echo "$REGISTER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('verification_token', ''))" 2>/dev/null)

    if [ -z "$VERIFICATION_TOKEN" ]; then
        log_error "No verification_token in response: $REGISTER_RESPONSE"
        return 1
    fi

    log_success "User registered, verification_token: ${VERIFICATION_TOKEN:0:20}..."

    # -----------------------------------------------------------------------
    # Step 2: Get verification code from Redis
    # -----------------------------------------------------------------------
    log_info "Step 2/4: Retrieving verification code from Redis..."

    # Check if running in Docker or local
    # Auth-API uses its own Redis container (auth-redis)
    if docker ps --format "{{.Names}}" | grep -q "^auth-redis$"; then
        # Auth-API Redis (no password)
        CODE_DATA=$(docker exec auth-redis redis-cli GET "verify_token:$VERIFICATION_TOKEN" 2>/dev/null || echo "")
    elif docker ps --format "{{.Names}}" | grep -q "activity-redis"; then
        # Infrastructure Redis (with password)
        CODE_DATA=$(docker exec activity-redis redis-cli --no-auth-warning -a redis_secure_pass_change_me GET "verify_token:$VERIFICATION_TOKEN" 2>/dev/null || echo "")
    else
        # Local Redis
        CODE_DATA=$(redis-cli GET "verify_token:$VERIFICATION_TOKEN" 2>/dev/null || echo "")
    fi

    if [ -z "$CODE_DATA" ]; then
        log_error "Could not retrieve verification code from Redis"
        log_error "Tried key: verify_token:$VERIFICATION_TOKEN"
        return 1
    fi

    # Parse code from Redis data (format: "user_id:code" or "email:code")
    VERIFICATION_CODE=$(echo "$CODE_DATA" | cut -d':' -f2)

    if [ -z "$VERIFICATION_CODE" ]; then
        log_error "Could not parse verification code from Redis data: $CODE_DATA"
        return 1
    fi

    log_success "Verification code retrieved: $VERIFICATION_CODE"

    # -----------------------------------------------------------------------
    # Step 3: Verify email
    # -----------------------------------------------------------------------
    log_info "Step 3/4: Verifying email..."

    VERIFY_RESPONSE=$(curl -sS -X POST "$AUTH_API_URL/api/auth/verify-code" \
        -H "Content-Type: application/json" \
        -d "{\"verification_token\": \"$VERIFICATION_TOKEN\", \"code\": \"$VERIFICATION_CODE\"}")

    if ! echo "$VERIFY_RESPONSE" | grep -qi "verified\|success"; then
        log_error "Email verification failed: $VERIFY_RESPONSE"
        return 1
    fi

    log_success "Email verified successfully"

    # -----------------------------------------------------------------------
    # Step 4: Login to get JWT token
    # -----------------------------------------------------------------------
    log_info "Step 4/4: Logging in to get JWT token..."

    LOGIN_RESPONSE=$(curl -sS -X POST "$AUTH_API_URL/api/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\": \"$TEST_USER_EMAIL\", \"password\": \"$TEST_PASSWORD\"}")

    # Extract access token
    TEST_ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

    if [ -z "$TEST_ACCESS_TOKEN" ]; then
        log_error "No access_token in login response: $LOGIN_RESPONSE"
        return 1
    fi

    # Extract user_id from JWT token (decode without verification for testing)
    TEST_USER_ID=$(python3 -c "
import sys, json, base64
token = '$TEST_ACCESS_TOKEN'
parts = token.split('.')
if len(parts) >= 2:
    # Add padding if needed
    payload = parts[1]
    payload += '=' * (4 - len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload)
    data = json.loads(decoded)
    print(data.get('sub', ''))
" 2>/dev/null)

    if [ -z "$TEST_USER_ID" ]; then
        log_error "Could not extract user_id from JWT token"
        return 1
    fi

    log_success "Login successful!"
    log_success "User ID: $TEST_USER_ID"
    log_success "Email: $TEST_USER_EMAIL"
    log_success "Access Token: ${TEST_ACCESS_TOKEN:0:30}..."

    # Export variables for use by calling script
    export TEST_USER_ID
    export TEST_USER_EMAIL
    export TEST_ACCESS_TOKEN
    export TEST_PASSWORD

    return 0
}

# ═══════════════════════════════════════════════════════════════════════════
# EXECUTE
# ═══════════════════════════════════════════════════════════════════════════

# Only execute if not being sourced
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being executed directly
    create_test_user_with_token

    echo ""
    echo "════════════════════════════════════════════"
    echo "  Test User Created Successfully"
    echo "════════════════════════════════════════════"
    echo "User ID:      $TEST_USER_ID"
    echo "Email:        $TEST_USER_EMAIL"
    echo "Password:     $TEST_PASSWORD"
    echo "Access Token: ${TEST_ACCESS_TOKEN:0:50}..."
    echo ""
    echo "Use these credentials for testing:"
    echo "  export TEST_USER_ID='$TEST_USER_ID'"
    echo "  export TEST_ACCESS_TOKEN='$TEST_ACCESS_TOKEN'"
    echo "════════════════════════════════════════════"
else
    # Script is being sourced - just create user quietly
    create_test_user_with_token >&2 || {
        log_error "Failed to create test user"
        return 1
    }
fi
