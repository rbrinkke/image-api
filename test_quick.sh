#!/usr/bin/env bash
#
# Image Processor - Quick Verification Test
# Tests core functionality in < 30 seconds
#

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

API_URL="http://localhost:8002"  # image-api runs on port 8002 (write-api uses 8000)
PASSED=0
FAILED=0

echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  IMAGE PROCESSOR - QUICK VERIFICATION TEST     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}\n"

# Generate JWT
echo -n "🔐 Generating JWT token... "
JWT_SECRET="9c1e3ddbc3c2dfb6d3f167f9c2298902da5dbb8381405b2cbc4e827fe0fca5b4"
JWT_TOKEN=$(python3 -c "import jwt; print(jwt.encode({'sub': 'test-user'}, '$JWT_SECRET', algorithm='HS256'))")
if [ -n "$JWT_TOKEN" ]; then
    echo -e "${GREEN}✓${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗${NC}"
    ((FAILED++))
    exit 1
fi

# Test 1: Health Check
echo -n "🏥 API Health Check... "
response=$(curl -sL "$API_URL/api/v1/health" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null)
if [ "$response" == "healthy" ]; then
    echo -e "${GREEN}✓ HEALTHY${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC}"
    ((FAILED++))
fi

# Test 2: Database
echo -n "💾 Database Tables... "
tables=$(sqlite3 /data/processor.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null)
if [ "$tables" -ge "3" ]; then
    echo -e "${GREEN}✓ $tables tables${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ Only $tables tables${NC}"
    ((FAILED++))
fi

# Test 3: Redis
echo -n "📦 Redis Connection... "
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PONG${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ No response${NC}"
    ((FAILED++))
fi

# Test 4: Storage Directory
echo -n "📁 Storage Directory... "
if [ -d "/data/storage" ]; then
    echo -e "${GREEN}✓ EXISTS${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ MISSING${NC}"
    ((FAILED++))
fi

# Test 5: Upload Small Image
echo -n "📤 Image Upload (small JPEG)... "
upload_response=$(curl -sL -X POST \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -F "file=@test_images/small_square_jpeg.jpeg" \
    -F "bucket=test-uploads" \
    "$API_URL/api/v1/images/upload" 2>/dev/null)

JOB_ID=$(echo "$upload_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))" 2>/dev/null)
IMAGE_ID=$(echo "$upload_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('image_id', ''))" 2>/dev/null)

if [ -n "$JOB_ID" ] && [ -n "$IMAGE_ID" ]; then
    echo -e "${GREEN}✓ Accepted (job: ${JOB_ID:0:8}...)${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC}"
    ((FAILED++))
fi

# Test 6: Job Status
echo -n "🔍 Job Status Check... "
job_status=$(curl -sL "$API_URL/api/v1/images/jobs/$JOB_ID" 2>/dev/null | \
    python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null)

if [ -n "$job_status" ]; then
    echo -e "${GREEN}✓ Status: $job_status${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ No status${NC}"
    ((FAILED++))
fi

# Test 7: Wait for Processing (max 20 seconds)
echo -n "⏳ Waiting for processing... "
max_wait=20
waited=0
while [ $waited -lt $max_wait ]; do
    status=$(curl -sL "$API_URL/api/v1/images/jobs/$JOB_ID" 2>/dev/null | \
        python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null)

    if [ "$status" == "completed" ]; then
        echo -e "${GREEN}✓ COMPLETED (${waited}s)${NC}"
        ((PASSED++))
        break
    elif [ "$status" == "failed" ]; then
        echo -e "${RED}✗ FAILED${NC}"
        ((FAILED++))
        break
    fi

    sleep 1
    ((waited++))
    echo -n "."
done

if [ $waited -eq $max_wait ]; then
    echo -e "${RED}✗ TIMEOUT${NC}"
    ((FAILED++))
fi

# Test 8: Retrieve Results
if [ "$status" == "completed" ]; then
    echo -n "🎨 Retrieve Results... "
    result=$(curl -sL "$API_URL/api/v1/images/jobs/$JOB_ID/result" 2>/dev/null)
    urls=$(echo "$result" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('urls', {})))" 2>/dev/null)

    if [ "$urls" == "4" ]; then
        echo -e "${GREEN}✓ All 4 variants${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Only $urls variants${NC}"
        ((FAILED++))
    fi

    # Test 9: Dominant Color
    echo -n "🎨 Dominant Color Extraction... "
    color=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('metadata', {}).get('dominant_color', ''))" 2>/dev/null)

    if [[ $color =~ ^#[0-9A-Fa-f]{6}$ ]]; then
        echo -e "${GREEN}✓ $color${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Invalid: $color${NC}"
        ((FAILED++))
    fi

    # Test 10: Image Retrieval
    echo -n "🖼️  Image Retrieval by ID... "
    img_response=$(curl -sL "$API_URL/api/v1/images/$IMAGE_ID?size=medium" 2>/dev/null | \
        python3 -c "import sys, json; print(json.load(sys.stdin).get('image_id', ''))" 2>/dev/null)

    if [ "$img_response" == "$IMAGE_ID" ]; then
        echo -e "${GREEN}✓ Found${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Not found${NC}"
        ((FAILED++))
    fi
fi

# Test 11: Statistics Endpoint
echo -n "📊 Statistics Endpoint... "
stats=$(curl -sL "$API_URL/api/v1/health/stats" 2>/dev/null | \
    python3 -c "import sys, json; print(json.load(sys.stdin).get('storage', {}).get('total_jobs', 0))" 2>/dev/null)

if [ "$stats" -ge "1" ]; then
    echo -e "${GREEN}✓ $stats jobs logged${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ No stats${NC}"
    ((FAILED++))
fi

# Test 12: Service Info
echo -n "ℹ️  Service Info... "
service_name=$(curl -sL "$API_URL/info" 2>/dev/null | \
    python3 -c "import sys, json; print(json.load(sys.stdin).get('service', {}).get('name', ''))" 2>/dev/null)

if [ "$service_name" == "image-processor" ]; then
    echo -e "${GREEN}✓ Verified${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ Wrong name${NC}"
    ((FAILED++))
fi

# Test 13: Error Handling - Invalid File
echo -n "🚫 Error Handling (invalid file)... "
echo "not an image" > /tmp/fake.txt
error_response=$(curl -sL -w "\n%{http_code}" -X POST \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -F "file=@/tmp/fake.txt" \
    -F "bucket=test" \
    "$API_URL/api/v1/images/upload" 2>/dev/null | tail -1)

if [ "$error_response" == "415" ]; then
    echo -e "${GREEN}✓ 415 Unsupported Media Type${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ Got HTTP $error_response${NC}"
    ((FAILED++))
fi

# Test 14: Services Running
echo -n "🔄 All Services Running... "
service_count=$(ps aux | grep -E "(uvicorn|celery|redis)" | grep -v grep | wc -l)
if [ "$service_count" -ge "4" ]; then
    echo -e "${GREEN}✓ $service_count processes${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ Only $service_count processes${NC}"
    ((FAILED++))
fi

# Summary
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "Total Tests: $((PASSED + FAILED))"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"

if [ $FAILED -eq 0 ]; then
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   ✅ ALL TESTS PASSED - 100% WORKING!     ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
    echo ""
    exit 0
else
    echo ""
    echo -e "${RED}╔════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║   ❌ SOME TESTS FAILED                     ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════╝${NC}"
    echo ""
    exit 1
fi
