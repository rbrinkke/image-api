#!/usr/bin/env bash
#
# tests/test_rbac_security.sh
#
# Verification of Strict Ownership & RBAC Model
#
# Usage: ./tests/test_rbac_security.sh
# Exit: 0 = all pass, 1 = any fail
#

set -uo pipefail

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

API_URL="http://localhost:8004"
# Secret from docker-compose.yml
JWT_SECRET="your_very_long_secret_key_at_least_32_characters"
ORG_ID="1"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

PASSED_TESTS=0
FAILED_TESTS=0

# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

log_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_pass() { echo -e "${GREEN}✅ PASS:${NC} $1"; PASSED_TESTS=$((PASSED_TESTS + 1)); }
log_fail() { echo -e "${RED}❌ FAIL:${NC} $1"; FAILED_TESTS=$((FAILED_TESTS + 1)); }

generate_jwt() {
    local user_id="$1"
    local permissions="$2"  # JSON array string, e.g. '["image:upload"]'
    
    python3 -c "
import jwt
import time
import json

payload = {
    'sub': '$user_id',
    'org_id': '$ORG_ID',
    'permissions': $permissions,
    'exp': time.time() + 3600,
    'iat': time.time()
}
print(jwt.encode(payload, '$JWT_SECRET', algorithm='HS256'))
"
}

ensure_test_image() {
    mkdir -p test_images
    if [ ! -f "test_images/security_test.jpg" ]; then
        log_info "Generating test image..."
        # Create a simple dummy image file (valid enough for upload if not strictly validated as image content, 
        # but to be safe we copy one if exists or make a minimal valid jpg header?)
        # Actually, the API validates mime types.
        # Let's try to create a real minimal jpeg using python if possible, or just random bytes if the API only checks extension/header?
        # API uses PIL to open it, so it needs to be valid.
        
        python3 -c "
from PIL import Image
img = Image.new('RGB', (100, 100), color='red')
img.save('test_images/security_test.jpg')
" || {
            log_info "PIL not installed locally, checking if we can use existing images..."
            if [ -f "test_images/small_square_jpeg.jpeg" ]; then
                cp "test_images/small_square_jpeg.jpeg" "test_images/security_test.jpg"
            else
                 echo "Error: No test image available and cannot generate one."
                 exit 1
            fi
        }
    fi
}

wait_for_job() {
    local job_id="$1"
    local token="$2"
    local max_retries=30
    local count=0
    
    log_info "Waiting for job $job_id to complete..."
    
    while [ $count -lt $max_retries ]; do
        STATUS_RESP=$(curl -s -H "Authorization: Bearer $token" "${API_URL}/api/v1/images/jobs/${job_id}")
        STATUS=$(echo "$STATUS_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null)
        
        if [ "$STATUS" == "completed" ]; then
            log_info "Job completed."
            return 0
        elif [ "$STATUS" == "failed" ]; then
            log_fail "Job failed processing."
            return 1
        fi
        
        sleep 1
        count=$((count + 1))
    done
    
    log_fail "Job timed out."
    return 1
}

# ═══════════════════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════════════════

log_info "Setting up security test environment..."
ensure_test_image

# 1. Create Tokens
log_info "Generating User Tokens..."

# User A: Normal user
TOKEN_A=$(generate_jwt "user_a" '["image:upload","image:read"]')

# User B: Attacker (Normal user)
TOKEN_B=$(generate_jwt "user_b" '["image:upload","image:read"]')

# Admin: Has admin permission
TOKEN_ADMIN=$(generate_jwt "user_admin" '["image:admin","image:upload","image:read"]')

# Bucket: System bucket (Accessible by all, so we test ownership logic specifically)
BUCKET="org-${ORG_ID}/system/"

# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 1: The "Hacker" Test
# User A uploads, User B tries to delete.
# ═══════════════════════════════════════════════════════════════════════════

log_info "--- Scenario 1: The Hacker Test ---"

# Step 1: User A uploads
UPLOAD_RESP=$(curl -s -S -X POST "${API_URL}/api/v1/images/upload" \
    -H "Authorization: Bearer ${TOKEN_A}" \
    -F "file=@test_images/security_test.jpg" \
    -F "bucket=${BUCKET}")
CURL_EXIT=$?

if [ $CURL_EXIT -ne 0 ] || [ -z "$UPLOAD_RESP" ]; then
    log_fail "Setup failed: User A could not upload image. Curl exit code: $CURL_EXIT"
    echo "Response: $UPLOAD_RESP"
    exit 1
fi

IMAGE_ID_A1=$(echo "$UPLOAD_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('image_id', ''))" 2>/dev/null)
JOB_ID_A1=$(echo "$UPLOAD_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))" 2>/dev/null)

if [ -z "$IMAGE_ID_A1" ]; then
    log_fail "Setup failed: User A could not upload image (No image_id in response)."
    echo "Response: $UPLOAD_RESP"
    exit 1
else
    log_info "User A uploaded image: $IMAGE_ID_A1 (Job: $JOB_ID_A1)"
    wait_for_job "$JOB_ID_A1" "$TOKEN_A"
fi

# Step 2: User B tries to delete
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "${API_URL}/api/v1/images/${IMAGE_ID_A1}" \
    -H "Authorization: Bearer ${TOKEN_B}")

if [ "$HTTP_CODE" == "403" ]; then
    log_pass "User B denied deletion of User A's image (403 Forbidden)."
else
    log_fail "User B was NOT denied! HTTP Code: $HTTP_CODE"
fi

# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 2: The Owner Test
# User A tries to delete their own image.
# ═══════════════════════════════════════════════════════════════════════════

log_info "--- Scenario 2: The Owner Test ---"

# User A deletes their own image
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "${API_URL}/api/v1/images/${IMAGE_ID_A1}" \
    -H "Authorization: Bearer ${TOKEN_A}")

if [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "202" ] || [ "$HTTP_CODE" == "204" ]; then
    log_pass "User A successfully deleted their own image ($HTTP_CODE)."
    
    # Verify it's gone
    HTTP_CODE_CHECK=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/api/v1/images/${IMAGE_ID_A1}" \
        -H "Authorization: Bearer ${TOKEN_A}")
    if [ "$HTTP_CODE_CHECK" == "404" ]; then
        log_pass "Image verification: Image not found (404)."
    else
        log_fail "Image still exists after deletion! HTTP: $HTTP_CODE_CHECK"
    fi
else
    log_fail "User A failed to delete their own image. HTTP Code: $HTTP_CODE"
fi

# ═══════════════════════════════════════════════════════════════════════════
# SCENARIO 3: The Moderator Test
# User A uploads, Admin tries to delete.
# ═══════════════════════════════════════════════════════════════════════════

log_info "--- Scenario 3: The Moderator Test ---"

# Step 1: User A uploads another image
UPLOAD_RESP=$(curl -s -S -X POST "${API_URL}/api/v1/images/upload" \
    -H "Authorization: Bearer ${TOKEN_A}" \
    -F "file=@test_images/security_test.jpg" \
    -F "bucket=${BUCKET}")
CURL_EXIT=$?

if [ $CURL_EXIT -ne 0 ] || [ -z "$UPLOAD_RESP" ]; then
    log_fail "Setup failed: User A could not upload second image. Curl exit code: $CURL_EXIT"
    echo "Response: $UPLOAD_RESP"
    exit 1
fi

IMAGE_ID_A2=$(echo "$UPLOAD_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('image_id', ''))" 2>/dev/null)
JOB_ID_A2=$(echo "$UPLOAD_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('job_id', ''))" 2>/dev/null)

if [ -z "$IMAGE_ID_A2" ]; then
    log_fail "Setup failed: User A could not upload second image (No image_id)."
    echo "Response: $UPLOAD_RESP"
    exit 1
else
    log_info "User A uploaded image: $IMAGE_ID_A2 (Job: $JOB_ID_A2)"
    wait_for_job "$JOB_ID_A2" "$TOKEN_A"
fi

# Step 2: Admin tries to delete
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "${API_URL}/api/v1/images/${IMAGE_ID_A2}" \
    -H "Authorization: Bearer ${TOKEN_ADMIN}")

if [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "202" ] || [ "$HTTP_CODE" == "204" ]; then
    log_pass "Admin successfully deleted User A's image ($HTTP_CODE)."
else
    log_fail "Admin failed to delete image. HTTP Code: $HTTP_CODE"
fi

# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

echo ""
if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}🎉 ALL SECURITY TESTS PASSED! ($PASSED_TESTS/$PASSED_TESTS)${NC}"
    exit 0
else
    echo -e "${RED}❌ $FAILED_TESTS TESTS FAILED!${NC}"
    exit 1
fi
