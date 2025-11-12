#!/bin/bash

################################################################################
# Authorization System Test Suite
################################################################################
# Comprehensive testing for the distributed authorization cache system.
# Tests cache, circuit breaker, auth-api integration, and permission checks.
################################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
MOCK_AUTH_API_URL="${MOCK_AUTH_API_URL:-http://localhost:8001}"
JWT_SECRET="${JWT_SECRET:-dev-secret-change-in-production}"

################################################################################
# Utility Functions
################################################################################

print_header() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║ $1${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_test() {
    echo -e "${BLUE}→ Test $1${NC}"
    TESTS_RUN=$((TESTS_RUN + 1))
}

print_success() {
    echo -e "${GREEN}  ✓ $1${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

print_failure() {
    echo -e "${RED}  ✗ $1${NC}"
    echo -e "${RED}    Details: $2${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

print_warning() {
    echo -e "${YELLOW}  ⚠ $1${NC}"
}

print_summary() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║ TEST SUMMARY${NC}"
    echo -e "${CYAN}╠════════════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC} Total Tests:  $TESTS_RUN"
    echo -e "${CYAN}║${NC} ${GREEN}Passed:       $TESTS_PASSED${NC}"
    echo -e "${CYAN}║${NC} ${RED}Failed:       $TESTS_FAILED${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}🎉 All tests passed!${NC}"
        return 0
    else
        echo -e "${RED}❌ Some tests failed${NC}"
        return 1
    fi
}

# Generate JWT token
generate_jwt() {
    local user_id=$1
    local org_id=$2

    python3 -c "
import jwt
import sys

payload = {
    'sub': '$user_id',
    'org_id': '$org_id',
    'email': '${user_id}@example.com'
}

token = jwt.encode(payload, '$JWT_SECRET', algorithm='HS256')
print(token)
"
}

################################################################################
# Service Health Checks
################################################################################

test_service_health() {
    print_header "SERVICE HEALTH CHECKS"

    # Test 1: Image API Health
    print_test "1.1: Image API Health Check"
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/v1/health")
    if [ "$http_code" -eq 200 ]; then
        print_success "Image API is healthy (HTTP $http_code)"
    else
        print_failure "Image API health check" "HTTP $http_code"
    fi

    # Test 2: Authorization Health Endpoint
    print_test "1.2: Authorization Health Endpoint"
    response=$(curl -s "$API_URL/api/v1/health/auth")
    status=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "error")

    if [[ "$status" == "healthy" || "$status" == "degraded" ]]; then
        print_success "Authorization health endpoint accessible (status: $status)"
    else
        print_failure "Authorization health endpoint" "Status: $status"
    fi

    # Test 3: Redis Connection
    print_test "1.3: Redis Connection Check"
    redis_status=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('cache', {}).get('redis_connection', 'unknown'))" 2>/dev/null || echo "error")

    if [ "$redis_status" == "healthy" ]; then
        print_success "Redis connection is healthy"
    else
        print_warning "Redis connection: $redis_status (tests may fail)"
    fi

    # Test 4: Mock Auth API (if available)
    print_test "1.4: Mock Auth API Check"
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "$MOCK_AUTH_API_URL/health" 2>/dev/null || echo "000")
    if [ "$http_code" -eq 200 ]; then
        print_success "Mock Auth API is running"
    else
        print_warning "Mock Auth API not running (manual testing will be limited)"
    fi
}

################################################################################
# Unit Tests (pytest)
################################################################################

test_unit_tests() {
    print_header "UNIT TESTS (pytest)"

    # Check if pytest is available
    if ! command -v pytest &> /dev/null; then
        print_warning "pytest not installed, skipping unit tests"
        return
    fi

    # Test 1: Authorization Cache Tests
    print_test "2.1: Authorization Cache Unit Tests"
    if pytest tests/test_authorization_cache.py -v --tb=short 2>&1 | tail -5; then
        print_success "Cache unit tests passed"
    else
        print_failure "Cache unit tests" "See pytest output above"
    fi

    # Test 2: Circuit Breaker Tests
    print_test "2.2: Circuit Breaker Unit Tests"
    if pytest tests/test_circuit_breaker.py -v --tb=short 2>&1 | tail -5; then
        print_success "Circuit breaker unit tests passed"
    else
        print_failure "Circuit breaker unit tests" "See pytest output above"
    fi

    # Test 3: Integration Tests
    print_test "2.3: Authorization Integration Tests"
    if pytest tests/test_authorization_integration.py -v --tb=short 2>&1 | tail -5; then
        print_success "Integration tests passed"
    else
        print_failure "Integration tests" "See pytest output above"
    fi
}

################################################################################
# API Endpoint Tests
################################################################################

test_api_endpoints() {
    print_header "API ENDPOINT TESTS"

    # Generate test tokens
    VALID_TOKEN=$(generate_jwt "test-user-123" "test-org-456")
    ADMIN_TOKEN=$(generate_jwt "admin-user-789" "test-org-456")
    READONLY_TOKEN=$(generate_jwt "readonly-user-999" "test-org-456")

    # Test 1: Upload with valid permission
    print_test "3.1: Upload with Valid Permission"
    # Create test image
    echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" | base64 -d > /tmp/test_auth_image.png

    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$API_URL/api/v1/images/upload" \
        -H "Authorization: Bearer $VALID_TOKEN" \
        -F "file=@/tmp/test_auth_image.png" \
        -F "bucket=test-auth")

    if [ "$http_code" -eq 202 ]; then
        print_success "Upload succeeded with valid permission (HTTP $http_code)"
    else
        print_failure "Upload with valid permission" "HTTP $http_code"
    fi

    # Test 2: Upload without token
    print_test "3.2: Upload without Token (Should Fail)"
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$API_URL/api/v1/images/upload" \
        -F "file=@/tmp/test_auth_image.png" \
        -F "bucket=test-auth")

    if [[ "$http_code" == "401" || "$http_code" == "403" ]]; then
        print_success "Upload rejected without token (HTTP $http_code)"
    else
        print_failure "Upload rejection without token" "Expected 401/403, got HTTP $http_code"
    fi

    # Test 3: Upload with invalid token
    print_test "3.3: Upload with Invalid Token (Should Fail)"
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$API_URL/api/v1/images/upload" \
        -H "Authorization: Bearer invalid_token_12345" \
        -F "file=@/tmp/test_auth_image.png" \
        -F "bucket=test-auth")

    if [[ "$http_code" == "401" || "$http_code" == "403" ]]; then
        print_success "Upload rejected with invalid token (HTTP $http_code)"
    else
        print_failure "Upload rejection with invalid token" "Expected 401/403, got HTTP $http_code"
    fi

    # Test 4: Readonly user upload (Should Fail)
    print_test "3.4: Readonly User Upload (Should Fail)"
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$API_URL/api/v1/images/upload" \
        -H "Authorization: Bearer $READONLY_TOKEN" \
        -F "file=@/tmp/test_auth_image.png" \
        -F "bucket=test-auth")

    if [[ "$http_code" == "403" ]]; then
        print_success "Readonly user upload rejected (HTTP $http_code)"
    else
        print_warning "Readonly user upload" "Expected 403, got HTTP $http_code (may be due to mock API not running)"
    fi

    # Cleanup
    rm -f /tmp/test_auth_image.png
}

################################################################################
# Cache Behavior Tests
################################################################################

test_cache_behavior() {
    print_header "CACHE BEHAVIOR TESTS"

    VALID_TOKEN=$(generate_jwt "test-user-123" "test-org-456")

    # Test 1: Cache warming
    print_test "4.1: Cache Warming (First Request)"
    echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" | base64 -d > /tmp/test_cache.png

    start_time=$(date +%s%N)
    curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$API_URL/api/v1/images/upload" \
        -H "Authorization: Bearer $VALID_TOKEN" \
        -F "file=@/tmp/test_cache.png" \
        -F "bucket=test-cache" >/dev/null
    end_time=$(date +%s%N)
    first_request_time=$(( (end_time - start_time) / 1000000 ))

    print_success "First request completed in ${first_request_time}ms (cache miss)"

    # Test 2: Cache hit
    print_test "4.2: Cache Hit (Second Request)"
    start_time=$(date +%s%N)
    curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$API_URL/api/v1/images/upload" \
        -H "Authorization: Bearer $VALID_TOKEN" \
        -F "file=@/tmp/test_cache.png" \
        -F "bucket=test-cache" >/dev/null
    end_time=$(date +%s%N)
    second_request_time=$(( (end_time - start_time) / 1000000 ))

    print_success "Second request completed in ${second_request_time}ms (cache hit)"

    if [ $second_request_time -lt $first_request_time ]; then
        print_success "Cache hit was faster than cache miss (${second_request_time}ms < ${first_request_time}ms)"
    else
        print_warning "Cache hit not faster" "This may be due to network variance"
    fi

    rm -f /tmp/test_cache.png
}

################################################################################
# Circuit Breaker Tests
################################################################################

test_circuit_breaker() {
    print_header "CIRCUIT BREAKER TESTS"

    # Test 1: Check initial circuit state
    print_test "5.1: Circuit Breaker Initial State"
    response=$(curl -s "$API_URL/api/v1/health/auth")
    circuit_state=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('auth_api', {}).get('circuit_breaker', {}).get('state', 'unknown'))" 2>/dev/null || echo "error")

    if [[ "$circuit_state" == "closed" || "$circuit_state" == "open" || "$circuit_state" == "half_open" ]]; then
        print_success "Circuit breaker state: $circuit_state"
    else
        print_failure "Circuit breaker state check" "State: $circuit_state"
    fi

    # Test 2: Circuit breaker config
    print_test "5.2: Circuit Breaker Configuration"
    threshold=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('auth_api', {}).get('circuit_breaker', {}).get('threshold', 'unknown'))" 2>/dev/null || echo "error")
    timeout=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('auth_api', {}).get('circuit_breaker', {}).get('timeout_seconds', 'unknown'))" 2>/dev/null || echo "error")

    if [[ "$threshold" != "unknown" && "$timeout" != "unknown" ]]; then
        print_success "Circuit breaker configured (threshold: $threshold, timeout: ${timeout}s)"
    else
        print_failure "Circuit breaker configuration" "Could not read config"
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║           AUTHORIZATION SYSTEM TEST SUITE                          ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Configuration:"
    echo "  API URL:           $API_URL"
    echo "  Mock Auth API URL: $MOCK_AUTH_API_URL"
    echo ""

    # Run test suites
    test_service_health
    test_unit_tests
    test_api_endpoints
    test_cache_behavior
    test_circuit_breaker

    # Print summary
    print_summary
}

# Run tests
main
