#!/usr/bin/env bash
#
# Image Processor Service - Comprehensive Test Suite
# =====================================================
# Tests all aspects of the image processing microservice
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_URL="http://localhost:8000"
TEST_IMAGES_DIR="test_images"
TEST_BUCKET="test-uploads"
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Test results
declare -a FAILED_TEST_NAMES

# Helper functions
print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}\n"
}

print_test() {
    echo -e "${YELLOW}🧪 TEST: $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ PASS: $1${NC}"
    ((PASSED_TESTS++))
    ((TOTAL_TESTS++))
}

print_failure() {
    echo -e "${RED}❌ FAIL: $1${NC}"
    echo -e "${RED}   Error: $2${NC}"
    FAILED_TEST_NAMES+=("$1: $2")
    ((FAILED_TESTS++))
    ((TOTAL_TESTS++))
}

# Generate JWT token for testing
generate_jwt() {
    python3 << 'EOF'
import jwt
import sys

try:
    token = jwt.encode(
        {'sub': 'test-user-123', 'username': 'test_user'},
        'dev-secret-change-in-production',
        algorithm='HS256'
    )
    print(token)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

# Wait for job completion
wait_for_job() {
    local job_id=$1
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        local status=$(curl -sL -H "Authorization: Bearer $JWT_TOKEN" \
            "$API_URL/api/v1/images/jobs/$job_id" | \
            python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))")

        if [ "$status" == "completed" ]; then
            return 0
        elif [ "$status" == "failed" ]; then
            return 1
        fi

        sleep 1
        ((attempt++))
    done

    return 2  # Timeout
}

# ============================================================================
# TEST 1: Infrastructure Health Checks
# ============================================================================
test_infrastructure() {
    print_header "TEST SUITE 1: Infrastructure Health"

    # Test 1.1: API Server Health
    print_test "1.1: API Server Health Endpoint"
    response=$(curl -sL -w "\n%{http_code}" "$API_URL/api/v1/health")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "200" ]; then
        service_name=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('service', ''))")
        if [ "$service_name" == "image-processor" ]; then
            print_success "API server is healthy"
        else
            print_failure "API server health check" "Unexpected service name: $service_name"
        fi
    else
        print_failure "API server health check" "HTTP $http_code"
    fi

    # Test 1.2: Redis Connectivity
    print_test "1.2: Redis Connectivity"
    if redis-cli ping > /dev/null 2>&1; then
        print_success "Redis is responding"
    else
        print_failure "Redis connectivity" "Redis not responding"
    fi

    # Test 1.3: Database Initialization
    print_test "1.3: Database Initialization"
    if [ -f "/data/processor.db" ]; then
        table_count=$(sqlite3 /data/processor.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
        if [ "$table_count" -ge "3" ]; then
            print_success "Database initialized with $table_count tables"
        else
            print_failure "Database initialization" "Only $table_count tables found"
        fi
    else
        print_failure "Database initialization" "Database file not found"
    fi

    # Test 1.4: Storage Directory
    print_test "1.4: Storage Directory Setup"
    if [ -d "/data/storage" ]; then
        print_success "Storage directory exists"
    else
        print_failure "Storage directory" "Directory not found"
    fi
}

# ============================================================================
# TEST 2: Authentication & Security
# ============================================================================
test_authentication() {
    print_header "TEST SUITE 2: Authentication & Security"

    # Test 2.1: JWT Token Generation
    print_test "2.1: JWT Token Generation"
    JWT_TOKEN=$(generate_jwt)
    if [ -n "$JWT_TOKEN" ]; then
        print_success "JWT token generated successfully"
    else
        print_failure "JWT token generation" "Failed to generate token"
        return
    fi

    # Test 2.2: Authenticated Request
    print_test "2.2: Authenticated Request Acceptance"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        "$API_URL/api/v1/health")
    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "200" ]; then
        print_success "Authenticated request accepted"
    else
        print_failure "Authenticated request" "HTTP $http_code"
    fi

    # Test 2.3: Unauthenticated Request Rejection
    print_test "2.3: Unauthenticated Upload Rejection"
    response=$(curl -sL -w "\n%{http_code}" \
        -X POST \
        -F "file=@$TEST_IMAGES_DIR/small_square_jpeg.jpeg" \
        -F "bucket=$TEST_BUCKET" \
        "$API_URL/api/v1/images/upload")
    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "403" ] || [ "$http_code" == "401" ]; then
        print_success "Unauthenticated request rejected (HTTP $http_code)"
    else
        print_failure "Unauthenticated request rejection" "Expected 401/403, got HTTP $http_code"
    fi

    # Test 2.4: Invalid Token Rejection
    print_test "2.4: Invalid Token Rejection"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer invalid_token_12345" \
        -X POST \
        -F "file=@$TEST_IMAGES_DIR/small_square_jpeg.jpeg" \
        -F "bucket=$TEST_BUCKET" \
        "$API_URL/api/v1/images/upload")
    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "401" ]; then
        print_success "Invalid token rejected"
    else
        print_failure "Invalid token rejection" "Expected 401, got HTTP $http_code"
    fi
}

# ============================================================================
# TEST 3: Image Upload Flow
# ============================================================================
test_upload_flow() {
    print_header "TEST SUITE 3: Image Upload Flow"

    # Test 3.1: Small JPEG Upload
    print_test "3.1: Small JPEG Image Upload"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -X POST \
        -F "file=@$TEST_IMAGES_DIR/small_square_jpeg.jpeg" \
        -F "bucket=$TEST_BUCKET" \
        -F "metadata={\"test\":\"small_jpeg\"}" \
        "$API_URL/api/v1/images/upload")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "202" ]; then
        JOB_ID=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))")
        IMAGE_ID=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('image_id', ''))")

        if [ -n "$JOB_ID" ] && [ -n "$IMAGE_ID" ]; then
            print_success "Small JPEG uploaded (job_id: ${JOB_ID:0:8}...)"
            SMALL_JPEG_JOB_ID=$JOB_ID
            SMALL_JPEG_IMAGE_ID=$IMAGE_ID
        else
            print_failure "Small JPEG upload" "Missing job_id or image_id in response"
        fi
    else
        print_failure "Small JPEG upload" "HTTP $http_code"
    fi

    # Test 3.2: PNG Upload
    print_test "3.2: PNG Image Upload"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -X POST \
        -F "file=@$TEST_IMAGES_DIR/medium_square_png.png" \
        -F "bucket=$TEST_BUCKET" \
        "$API_URL/api/v1/images/upload")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "202" ]; then
        JOB_ID=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))")
        if [ -n "$JOB_ID" ]; then
            print_success "PNG uploaded (job_id: ${JOB_ID:0:8}...)"
            PNG_JOB_ID=$JOB_ID
        else
            print_failure "PNG upload" "Missing job_id"
        fi
    else
        print_failure "PNG upload" "HTTP $http_code"
    fi

    # Test 3.3: WebP Upload
    print_test "3.3: WebP Image Upload"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -X POST \
        -F "file=@$TEST_IMAGES_DIR/webp_test.webp" \
        -F "bucket=$TEST_BUCKET" \
        "$API_URL/api/v1/images/upload")

    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "202" ]; then
        print_success "WebP uploaded"
    else
        print_failure "WebP upload" "HTTP $http_code"
    fi

    # Test 3.4: Large Image Upload
    print_test "3.4: Large JPEG Image Upload"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -X POST \
        -F "file=@$TEST_IMAGES_DIR/large_landscape_jpeg.jpeg" \
        -F "bucket=$TEST_BUCKET" \
        "$API_URL/api/v1/images/upload")

    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "202" ]; then
        print_success "Large JPEG uploaded"
    else
        print_failure "Large JPEG upload" "HTTP $http_code"
    fi
}

# ============================================================================
# TEST 4: Job Status & Processing
# ============================================================================
test_job_processing() {
    print_header "TEST SUITE 4: Job Status & Processing"

    if [ -z "$SMALL_JPEG_JOB_ID" ]; then
        print_failure "Job processing tests" "No job_id available from upload tests"
        return
    fi

    # Test 4.1: Job Status Check
    print_test "4.1: Job Status Endpoint"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        "$API_URL/api/v1/images/jobs/$SMALL_JPEG_JOB_ID")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "200" ]; then
        status=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))")
        print_success "Job status retrieved: $status"
    else
        print_failure "Job status check" "HTTP $http_code"
    fi

    # Test 4.2: Wait for Job Completion
    print_test "4.2: Job Processing Completion"
    echo "   ⏳ Waiting for job processing..."

    if wait_for_job "$SMALL_JPEG_JOB_ID"; then
        print_success "Job completed successfully"
    else
        print_failure "Job completion" "Job failed or timed out"
        return
    fi

    # Test 4.3: Retrieve Results
    print_test "4.3: Retrieve Processing Results"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        "$API_URL/api/v1/images/jobs/$SMALL_JPEG_JOB_ID/result")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "200" ]; then
        urls=$(echo "$body" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('urls', {})))")
        if [ "$urls" == "4" ]; then
            print_success "Retrieved all 4 size variants"
        else
            print_failure "Processing results" "Expected 4 variants, got $urls"
        fi
    else
        print_failure "Processing results" "HTTP $http_code"
    fi

    # Test 4.4: Metadata Extraction
    print_test "4.4: Metadata Extraction (Dominant Color)"
    dominant_color=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('metadata', {}).get('dominant_color', ''))")

    if [[ $dominant_color =~ ^#[0-9A-Fa-f]{6}$ ]]; then
        print_success "Dominant color extracted: $dominant_color"
    else
        print_failure "Dominant color extraction" "Invalid color format: $dominant_color"
    fi
}

# ============================================================================
# TEST 5: Image Retrieval
# ============================================================================
test_image_retrieval() {
    print_header "TEST SUITE 5: Image Retrieval"

    if [ -z "$SMALL_JPEG_IMAGE_ID" ]; then
        print_failure "Image retrieval tests" "No image_id available"
        return
    fi

    # Test 5.1: Get Image Info
    print_test "5.1: Get Image Info by ID"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        "$API_URL/api/v1/images/$SMALL_JPEG_IMAGE_ID?size=medium")

    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "200" ]; then
        print_success "Image info retrieved"
    else
        print_failure "Image info retrieval" "HTTP $http_code"
    fi

    # Test 5.2: Get All Sizes
    print_test "5.2: Get All Size Variants"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        "$API_URL/api/v1/images/$SMALL_JPEG_IMAGE_ID/all")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "200" ]; then
        url_count=$(echo "$body" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('urls', {})))")
        if [ "$url_count" == "4" ]; then
            print_success "All size variants retrieved"
        else
            print_failure "All sizes retrieval" "Expected 4 sizes, got $url_count"
        fi
    else
        print_failure "All sizes retrieval" "HTTP $http_code"
    fi

    # Test 5.3: Non-existent Image
    print_test "5.3: Non-existent Image Handling"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        "$API_URL/api/v1/images/non-existent-id")

    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "404" ]; then
        print_success "Non-existent image returns 404"
    else
        print_failure "Non-existent image" "Expected 404, got HTTP $http_code"
    fi
}

# ============================================================================
# TEST 6: Error Handling
# ============================================================================
test_error_handling() {
    print_header "TEST SUITE 6: Error Handling"

    # Test 6.1: Invalid File Type
    print_test "6.1: Invalid File Type Rejection"
    echo "This is not an image" > /tmp/test.txt
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -X POST \
        -F "file=@/tmp/test.txt" \
        -F "bucket=$TEST_BUCKET" \
        "$API_URL/api/v1/images/upload")

    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "415" ]; then
        print_success "Invalid file type rejected (HTTP 415)"
    else
        print_failure "Invalid file type" "Expected 415, got HTTP $http_code"
    fi

    # Test 6.2: Missing File
    print_test "6.2: Missing File Parameter"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -X POST \
        -F "bucket=$TEST_BUCKET" \
        "$API_URL/api/v1/images/upload")

    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "422" ]; then
        print_success "Missing file parameter rejected (HTTP 422)"
    else
        print_failure "Missing file parameter" "Expected 422, got HTTP $http_code"
    fi
}

# ============================================================================
# TEST 7: Statistics & Monitoring
# ============================================================================
test_monitoring() {
    print_header "TEST SUITE 7: Statistics & Monitoring"

    # Test 7.1: Health Statistics
    print_test "7.1: Health Statistics Endpoint"
    response=$(curl -sL -w "\n%{http_code}" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        "$API_URL/api/v1/health/stats")

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)

    if [ "$http_code" == "200" ]; then
        completed=$(echo "$body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status_breakdown', {}).get('completed', 0))")
        print_success "Health stats retrieved (completed jobs: $completed)"
    else
        print_failure "Health statistics" "HTTP $http_code"
    fi

    # Test 7.2: Service Info
    print_test "7.2: Service Info Endpoint"
    response=$(curl -sL -w "\n%{http_code}" "$API_URL/info")
    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" == "200" ]; then
        print_success "Service info retrieved"
    else
        print_failure "Service info" "HTTP $http_code"
    fi
}

# ============================================================================
# MAIN TEST EXECUTION
# ============================================================================
main() {
    clear
    echo -e "${BLUE}"
    cat << "EOF"
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║     IMAGE PROCESSOR SERVICE - COMPREHENSIVE TEST SUITE            ║
║     Production-Ready Microservice Testing                         ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}\n"

    echo "📋 Test Configuration:"
    echo "   API URL: $API_URL"
    echo "   Test Images: $TEST_IMAGES_DIR"
    echo "   Test Bucket: $TEST_BUCKET"
    echo ""

    # Run all test suites
    test_infrastructure
    test_authentication
    test_upload_flow
    test_job_processing
    test_image_retrieval
    test_error_handling
    test_monitoring

    # Final Report
    print_header "TEST RESULTS SUMMARY"

    echo -e "Total Tests: ${BLUE}$TOTAL_TESTS${NC}"
    echo -e "Passed:      ${GREEN}$PASSED_TESTS${NC}"
    echo -e "Failed:      ${RED}$FAILED_TESTS${NC}"

    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "\n${GREEN}╔════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║  ✅  ALL TESTS PASSED SUCCESSFULLY!  ✅   ║${NC}"
        echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}\n"
        exit 0
    else
        echo -e "\n${RED}╔════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  ❌  SOME TESTS FAILED  ❌                 ║${NC}"
        echo -e "${RED}╚════════════════════════════════════════════╝${NC}\n"

        echo -e "${RED}Failed Tests:${NC}"
        for failed in "${FAILED_TEST_NAMES[@]}"; do
            echo -e "  ${RED}• $failed${NC}"
        done
        echo ""
        exit 1
    fi
}

# Run main function
main "$@"
