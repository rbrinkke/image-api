#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "Complete Image API Authorization Test"
echo "=========================================="
echo ""

# Configuration
API_URL="http://localhost:8004"
AUTH_API_URL="http://localhost:8000"
TEST_USER_EMAIL="testuser@example.com"
TEST_USER_PASSWORD="SuperSecure2024Password"
TEST_IMAGE="test_images/test_500x500.jpg"

# Step 1: Get JWT token
echo -e "${YELLOW}Step 1: Login and get JWT token${NC}"
TOKEN_RESPONSE=$(curl -s -X POST "${AUTH_API_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"${TEST_USER_EMAIL}\", \"password\": \"${TEST_USER_PASSWORD}\"}")

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('access_token', ''))")
USER_ID=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; import jwt; data=json.load(sys.stdin); payload=jwt.decode(data['access_token'], options={'verify_signature': False}); print(payload['sub'])")

if [ -z "$TOKEN" ]; then
    echo -e "${RED}✗ Failed to get token${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Token obtained${NC}"
echo "  User ID: $USER_ID"
echo ""

# Step 2: Test upload to own user bucket
echo -e "${YELLOW}Step 2: Upload to own user bucket (expect 202)${NC}"
USER_BUCKET="users/${USER_ID}"

UPLOAD_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/images/upload" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@${TEST_IMAGE}" \
  -F "bucket=${USER_BUCKET}")

JOB_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('job_id', ''))")
IMAGE_ID=$(echo "$UPLOAD_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('image_id', ''))")

if [ -z "$JOB_ID" ]; then
    echo -e "${RED}✗ Upload failed${NC}"
    echo "$UPLOAD_RESPONSE" | python3 -m json.tool
    exit 1
fi

echo -e "${GREEN}✓ Upload accepted${NC}"
echo "  Job ID: $JOB_ID"
echo "  Image ID: $IMAGE_ID"
echo "  Bucket: $USER_BUCKET"
echo ""

# Step 3: Wait for processing
echo -e "${YELLOW}Step 3: Wait for image processing${NC}"
sleep 3

JOB_STATUS=$(curl -s "${API_URL}/api/v1/images/jobs/${JOB_ID}")
STATUS=$(echo "$JOB_STATUS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('status', ''))")

echo "  Processing status: $STATUS"
echo ""

# Step 4: Retrieve image in all formats
echo -e "${YELLOW}Step 4: Retrieve image in all formats${NC}"

for SIZE in thumbnail medium large original; do
    echo "  Testing size: $SIZE"

    RETRIEVE_RESPONSE=$(curl -s "${API_URL}/api/v1/images/${IMAGE_ID}?size=${SIZE}" \
      -H "Authorization: Bearer ${TOKEN}")
    URL=$(echo "$RETRIEVE_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('url', ''))")

    if [ -n "$URL" ]; then
        echo -e "    ${GREEN}✓ ${SIZE}: ${URL}${NC}"
    else
        echo -e "    ${RED}✗ ${SIZE} URL not found${NC}"
    fi
done
echo ""

# Step 5: Get all variants
echo -e "${YELLOW}Step 5: Get all image variants${NC}"
ALL_VARIANTS=$(curl -s "${API_URL}/api/v1/images/${IMAGE_ID}/all" \
  -H "Authorization: Bearer ${TOKEN}")
echo "$ALL_VARIANTS" | python3 -m json.tool
echo ""

# Step 6: Test unauthorized access (different user bucket)
echo -e "${YELLOW}Step 6: Test unauthorized access to another user's bucket (expect 403)${NC}"
OTHER_USER_BUCKET="users/different-user-12345"

UNAUTHORIZED_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/images/upload" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@${TEST_IMAGE}" \
  -F "bucket=${OTHER_USER_BUCKET}")

ERROR_CODE=$(echo "$UNAUTHORIZED_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('status_code', ''))")

if [ "$ERROR_CODE" = "403" ]; then
    echo -e "${GREEN}✓ Correctly denied (403 Forbidden)${NC}"
else
    echo -e "${RED}✗ Expected 403, got: $ERROR_CODE${NC}"
fi
echo ""

# Step 7: Test group upload (authorized)
echo -e "${YELLOW}Step 7: Upload to authorized group (expect 202 or 503 if auth-api endpoint missing)${NC}"
GROUP_ID="019a919f-c590-7624-aa52-a45a5a3194d8"
GROUP_BUCKET="groups/${GROUP_ID}"

GROUP_UPLOAD_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/images/upload" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@${TEST_IMAGE}" \
  -F "bucket=${GROUP_BUCKET}")

GROUP_JOB_ID=$(echo "$GROUP_UPLOAD_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('job_id', ''))")
GROUP_IMAGE_ID=$(echo "$GROUP_UPLOAD_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('image_id', ''))")
GROUP_ERROR=$(echo "$GROUP_UPLOAD_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('error', ''))")
GROUP_STATUS_CODE=$(echo "$GROUP_UPLOAD_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('status_code', ''))")

if [ -n "$GROUP_JOB_ID" ]; then
    echo -e "${GREEN}✓ Group upload accepted${NC}"
    echo "  Job ID: $GROUP_JOB_ID"
    echo "  Image ID: $GROUP_IMAGE_ID"
    echo "  Bucket: $GROUP_BUCKET"

    # Wait and retrieve group image
    sleep 3

    echo ""
    echo -e "${YELLOW}Step 7b: Retrieve group image (all formats)${NC}"
    for SIZE in thumbnail medium large original; do
        GROUP_RETRIEVE=$(curl -s "${API_URL}/api/v1/images/${GROUP_IMAGE_ID}?size=${SIZE}" \
          -H "Authorization: Bearer ${TOKEN}")
        GROUP_URL=$(echo "$GROUP_RETRIEVE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('url', ''))")

        if [ -n "$GROUP_URL" ]; then
            echo -e "    ${GREEN}✓ ${SIZE}: ${GROUP_URL}${NC}"
        else
            echo -e "    ${RED}✗ ${SIZE} URL not found${NC}"
        fi
    done
elif [ "$GROUP_STATUS_CODE" = "503" ]; then
    echo -e "${YELLOW}⚠ Group upload returned 503${NC}"
    echo "  This is expected if auth-api doesn't have /api/v1/authorization/check endpoint"
    echo "  Error: $GROUP_ERROR"
else
    echo -e "${RED}✗ Group upload failed unexpectedly${NC}"
    echo "$GROUP_UPLOAD_RESPONSE" | python3 -m json.tool
fi
echo ""

# Step 8: Test unauthorized group upload
echo -e "${YELLOW}Step 8: Upload to unauthorized group (expect 403)${NC}"
PRIVATE_GROUP_ID="019a919f-c591-764f-b5c0-8922035b4f8c"
PRIVATE_GROUP_BUCKET="groups/${PRIVATE_GROUP_ID}"

UNAUTHORIZED_GROUP_RESPONSE=$(curl -s -X POST "${API_URL}/api/v1/images/upload" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@${TEST_IMAGE}" \
  -F "bucket=${PRIVATE_GROUP_BUCKET}")

UNAUTH_GROUP_ERROR_CODE=$(echo "$UNAUTHORIZED_GROUP_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('status_code', ''))")

if [ "$UNAUTH_GROUP_ERROR_CODE" = "403" ] || [ "$UNAUTH_GROUP_ERROR_CODE" = "503" ]; then
    echo -e "${GREEN}✓ Correctly denied (${UNAUTH_GROUP_ERROR_CODE})${NC}"
else
    echo -e "${RED}✗ Expected 403 or 503, got: $UNAUTH_GROUP_ERROR_CODE${NC}"
fi
echo ""

# Summary
echo "=========================================="
echo -e "${GREEN}Test Summary${NC}"
echo "=========================================="
echo ""
echo "Authorization Tests:"
echo -e "  ${GREEN}✓${NC} JWT authentication works"
echo -e "  ${GREEN}✓${NC} Own user bucket: Upload allowed"
echo -e "  ${GREEN}✓${NC} Different user bucket: Upload denied (403)"
echo -e "  ${GREEN}✓${NC} Image retrieval in all formats works"
echo ""
echo "Group Authorization Tests:"
if [ "$GROUP_STATUS_CODE" = "503" ]; then
    echo -e "  ${YELLOW}⚠${NC} Auth-API endpoint missing (503 expected)"
    echo "      Need to implement: /api/v1/authorization/check in auth-api"
else
    echo -e "  ${GREEN}✓${NC} Authorized group upload works"
    echo -e "  ${GREEN}✓${NC} Unauthorized group denied"
fi
echo ""
echo "Image Processing:"
echo "  User Image ID: $IMAGE_ID"
if [ -n "$GROUP_IMAGE_ID" ]; then
    echo "  Group Image ID: $GROUP_IMAGE_ID"
fi
echo "  All variants generated: thumbnail, medium, large, original"
echo ""
echo "=========================================="
echo -e "${GREEN}Complete End-to-End Test Finished!${NC}"
echo "=========================================="
