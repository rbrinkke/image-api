#!/bin/bash
# =============================================================================
# Authorization Testing Utilities
# =============================================================================
# Provides helper functions for authorization E2E testing
# - Colored output for test results
# - HTTP status code assertions
# - Response time measurements
# - Redis cache inspection
# - Circuit breaker state checks
# =============================================================================

set -euo pipefail

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m' # No Color

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# =============================================================================
# Output Functions
# =============================================================================

print_header() {
    local title="$1"
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}$title${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""
}

print_section() {
    local title="$1"
    echo ""
    echo -e "${BLUE}--- $title ---${NC}"
}

print_success() {
    local message="$1"
    echo -e "${GREEN}✅ $message${NC}"
    ((TESTS_PASSED++))
}

print_error() {
    local message="$1"
    echo -e "${RED}❌ $message${NC}"
    ((TESTS_FAILED++))
}

print_warning() {
    local message="$1"
    echo -e "${YELLOW}⚠️  $message${NC}"
}

print_info() {
    local message="$1"
    echo -e "${CYAN}ℹ️  $message${NC}"
}

print_test_result() {
    local test_name="$1"
    local expected="$2"
    local actual="$3"

    echo -n "Test: $test_name ... "
    if [[ "$expected" == "$actual" ]]; then
        echo -e "${GREEN}✅ PASS${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        echo -e "  Expected: $expected"
        echo -e "  Actual:   $actual"
        ((TESTS_FAILED++))
        return 1
    fi
}

print_summary() {
    local total=$((TESTS_PASSED + TESTS_FAILED))
    echo ""
    print_header "Test Summary"
    echo "Total tests: $total"
    echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
    echo ""

    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}🎉 All tests passed!${NC}"
        return 0
    else
        echo -e "${RED}💥 Some tests failed${NC}"
        return 1
    fi
}

# =============================================================================
# HTTP Testing Functions
# =============================================================================

check_status_code() {
    local actual_status="$1"
    local expected_status="$2"
    local description="${3:-Status code check}"

    if [[ "$actual_status" == "$expected_status" ]]; then
        print_success "$description: $actual_status"
        return 0
    else
        print_error "$description: Expected $expected_status, got $actual_status"
        return 1
    fi
}

measure_response_time() {
    local url="$1"
    local method="${2:-GET}"
    local headers="${3:-}"

    local start_time=$(date +%s%3N)

    if [[ -n "$headers" ]]; then
        curl -s -X "$method" -H "$headers" "$url" > /dev/null
    else
        curl -s -X "$method" "$url" > /dev/null
    fi

    local end_time=$(date +%s%3N)
    local elapsed=$((end_time - start_time))

    echo "$elapsed"
}

extract_json_field() {
    local json="$1"
    local field="$2"

    echo "$json" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('$field', ''))"
}

# =============================================================================
# Redis Helper Functions
# =============================================================================

redis_exec() {
    local command="$1"
    local redis_password="${REDIS_PASSWORD:-redis_secure_pass_change_me}"

    docker exec image-processor-redis redis-cli \
        --no-auth-warning \
        -a "$redis_password" \
        $command
}

check_redis_cache() {
    local cache_key="$1"

    local value=$(redis_exec "GET $cache_key")

    if [[ -n "$value" && "$value" != "(nil)" ]]; then
        echo "$value"
        return 0
    else
        return 1
    fi
}

get_cache_ttl() {
    local cache_key="$1"

    local ttl=$(redis_exec "TTL $cache_key")

    if [[ "$ttl" -gt 0 ]]; then
        echo "$ttl"
        return 0
    else
        echo "0"
        return 1
    fi
}

list_auth_cache_keys() {
    redis_exec "KEYS auth:permission:*"
}

clear_auth_cache() {
    print_info "Clearing authorization cache..."
    redis_exec "DEL $(redis_exec 'KEYS auth:permission:*' | tr '\n' ' ')" || true
}

# =============================================================================
# Circuit Breaker Helper Functions
# =============================================================================

get_circuit_breaker_state() {
    redis_exec "GET auth:circuit_breaker:state" || echo "CLOSED"
}

get_circuit_breaker_failures() {
    redis_exec "GET auth:circuit_breaker:failures" || echo "0"
}

reset_circuit_breaker() {
    print_info "Resetting circuit breaker..."
    redis_exec "DEL auth:circuit_breaker:state"
    redis_exec "DEL auth:circuit_breaker:failures"
    redis_exec "DEL auth:circuit_breaker:opened_at"
}

print_circuit_breaker_status() {
    local state=$(get_circuit_breaker_state)
    local failures=$(get_circuit_breaker_failures)

    echo -e "${CYAN}Circuit Breaker Status:${NC}"
    echo "  State: $state"
    echo "  Failures: $failures"
}

# =============================================================================
# Service Health Functions
# =============================================================================

wait_for_service() {
    local service_name="$1"
    local health_url="$2"
    local max_attempts="${3:-30}"
    local wait_seconds="${4:-2}"

    print_info "Waiting for $service_name to be ready..."

    local attempt=1
    while [[ $attempt -le $max_attempts ]]; do
        if curl -s -f "$health_url" > /dev/null 2>&1; then
            print_success "$service_name is ready"
            return 0
        fi

        echo -n "."
        sleep "$wait_seconds"
        ((attempt++))
    done

    print_error "$service_name failed to start after $max_attempts attempts"
    return 1
}

check_service_health() {
    local service_name="$1"
    local health_url="$2"

    if curl -s -f "$health_url" > /dev/null 2>&1; then
        print_success "$service_name: healthy"
        return 0
    else
        print_error "$service_name: unhealthy"
        return 1
    fi
}

check_docker_service() {
    local container_name="$1"

    if docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
        print_success "Container $container_name: running"
        return 0
    else
        print_error "Container $container_name: not running"
        return 1
    fi
}

# =============================================================================
# Test Data Cleanup Functions
# =============================================================================

cleanup_test_uploads() {
    local storage_path="${STORAGE_PATH:-/data/storage}"

    print_info "Cleaning up test uploads..."

    # Clean up test organization buckets
    if [[ -d "$storage_path/org-test-org-001" ]]; then
        rm -rf "$storage_path/org-test-org-001"
        print_success "Removed test uploads"
    fi
}

cleanup_test_database() {
    print_info "Cleaning up test database entries..."

    # Connect to SQLite and delete test jobs
    docker exec image-processor-api sqlite3 /data/processor.db <<EOF
DELETE FROM processing_jobs WHERE metadata LIKE '%"test": true%';
DELETE FROM image_upload_events WHERE metadata LIKE '%"test": true%';
DELETE FROM upload_rate_limits WHERE user_id LIKE 'user-%-test';
EOF

    print_success "Removed test database entries"
}

cleanup_all() {
    print_section "Cleanup"
    clear_auth_cache
    reset_circuit_breaker
    cleanup_test_uploads
    cleanup_test_database
}

# =============================================================================
# JWT Token Functions
# =============================================================================

generate_jwt_token() {
    local user_id="$1"
    local org_id="$2"
    local email="$3"
    local jwt_secret="${JWT_SECRET_KEY:-dev-secret-change-in-production}"

    python3 -c "
import jwt
from datetime import datetime, timedelta

payload = {
    'sub': '$user_id',
    'org_id': '$org_id',
    'email': '$email',
    'aud': 'image-api',
    'iss': 'http://auth-api:8000',
    'exp': datetime.utcnow() + timedelta(hours=24)
}

token = jwt.encode(payload, '$jwt_secret', algorithm='HS256')
print(token)
"
}

# =============================================================================
# Export Functions
# =============================================================================

# Make functions available to scripts that source this file
export -f print_header
export -f print_section
export -f print_success
export -f print_error
export -f print_warning
export -f print_info
export -f print_test_result
export -f print_summary
export -f check_status_code
export -f measure_response_time
export -f extract_json_field
export -f redis_exec
export -f check_redis_cache
export -f get_cache_ttl
export -f list_auth_cache_keys
export -f clear_auth_cache
export -f get_circuit_breaker_state
export -f get_circuit_breaker_failures
export -f reset_circuit_breaker
export -f print_circuit_breaker_status
export -f wait_for_service
export -f check_service_health
export -f check_docker_service
export -f cleanup_test_uploads
export -f cleanup_test_database
export -f cleanup_all
export -f generate_jwt_token
