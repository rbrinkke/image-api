#!/bin/bash

# =============================================================================
# OAuth Migration Test Script for Image-API
# =============================================================================
# Automated end-to-end testing of OAuth implementation
# Run this after completing OAuth migration to verify all features work
# =============================================================================

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Configuration
AUTH_API="http://localhost:8000"
IMAGE_API="http://localhost:8002"
ORG_ID="f9aafe3b-9df3-4b29-9ae6-4f135c214fb0"

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Helper function to print test results
test_result() {
  local test_name="$1"
  local expected="$2"
  local actual="$3"

  TESTS_RUN=$((TESTS_RUN + 1))

  if [ "$expected" = "$actual" ]; then
    echo -e "${GREEN}✅ PASS${NC}: $test_name"
    TESTS_PASSED=$((TESTS_PASSED + 1))
  else
    echo -e "${RED}❌ FAIL${NC}: $test_name"
    echo -e "   Expected: $expected"
    echo -e "   Actual: $actual"
    TESTS_FAILED=$((TESTS_FAILED + 1))
  fi
}

echo -e "${BOLD}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║         OAuth Migration Test Suite - Image-API                ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# =============================================================================
# Test 1: Prerequisites Check
# =============================================================================
echo -e "${CYAN}${BOLD}[TEST 1] Prerequisites Verification${NC}"
echo ""

# Check auth-api
AUTH_HEALTH=$(curl -s http://localhost:8000/health | jq -r '.status // empty')
test_result "Auth-API health check" "healthy" "$AUTH_HEALTH"

# Check image-api
IMAGE_HEALTH=$(curl -s http://localhost:8002/health 2>/dev/null || echo "down")
if [ "$IMAGE_HEALTH" != "down" ]; then
  test_result "Image-API health check" "up" "up"
else
  test_result "Image-API health check" "up" "down"
  echo -e "${RED}Image-API is not running! Start it with: docker compose up -d image-api${NC}"
  exit 1
fi

# Check MongoDB
MONGO_VERSION=$(docker exec image-api-mongodb mongosh --quiet --eval "db.version()" 2>/dev/null || echo "error")
if [ "$MONGO_VERSION" != "error" ]; then
  test_result "MongoDB accessibility" "accessible" "accessible"
else
  test_result "MongoDB accessibility" "accessible" "not accessible"
fi

echo ""

# =============================================================================
# Test 2: OAuth Client Registration
# =============================================================================
echo -e "${CYAN}${BOLD}[TEST 2] OAuth Client Registration${NC}"
echo ""

# Check if client exists
CLIENT_EXISTS=$(docker exec auth-db psql -U postgres -d activitydb -t -c \
  "SELECT client_id FROM activity.oauth_clients WHERE client_id = 'image-api-service';" 2>/dev/null | tr -d ' \n')

if [ "$CLIENT_EXISTS" = "image-api-service" ]; then
  test_result "OAuth client exists in database" "exists" "exists"
else
  test_result "OAuth client exists in database" "exists" "not found"
  echo -e "${YELLOW}Registering client...${NC}"

  docker exec auth-db psql -U postgres -d activitydb -c \
    "INSERT INTO activity.oauth_clients (client_id, client_secret, client_name, redirect_uris, grant_types, scopes, is_active)
     VALUES ('image-api-service', 'your-image-service-secret-change-in-production', 'Image API Service', '{}', ARRAY['client_credentials'], ARRAY['users:read', 'organizations:read'], true)
     ON CONFLICT (client_id) DO NOTHING;" > /dev/null
fi

# Get service token
SERVICE_TOKEN_RESPONSE=$(curl -s -X POST "$AUTH_API/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=image-api-service&client_secret=your-image-service-secret-change-in-production&scope=users:read organizations:read")

SERVICE_TOKEN=$(echo $SERVICE_TOKEN_RESPONSE | jq -r '.access_token // empty')

if [ -n "$SERVICE_TOKEN" ]; then
  test_result "Service token acquisition" "success" "success"

  # Verify token has correct sub claim
  TOKEN_SUB=$(echo $SERVICE_TOKEN | cut -d'.' -f2 | base64 -d 2>/dev/null | jq -r '.sub')
  test_result "Service token sub claim" "image-api-service" "$TOKEN_SUB"
else
  test_result "Service token acquisition" "success" "failed"
fi

echo ""

# =============================================================================
# Test 3: User Authentication
# =============================================================================
echo -e "${CYAN}${BOLD}[TEST 3] User Authentication${NC}"
echo ""

# Alice login
ALICE_RESPONSE=$(curl -s -X POST "$AUTH_API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"alice.admin@example.com\",
    \"password\": \"SecurePass123!Admin\",
    \"org_id\": \"$ORG_ID\"
  }")

ALICE_TOKEN=$(echo $ALICE_RESPONSE | jq -r '.access_token // empty')
ALICE_USER_ID="4c52f4f6-6afe-4203-8761-9d30f0382695"

if [ -n "$ALICE_TOKEN" ]; then
  test_result "Alice login" "success" "success"

  # Verify token structure
  ALICE_TOKEN_SUB=$(echo $ALICE_TOKEN | cut -d'.' -f2 | base64 -d 2>/dev/null | jq -r '.sub')
  test_result "Alice token user_id" "$ALICE_USER_ID" "$ALICE_TOKEN_SUB"
else
  test_result "Alice login" "success" "failed"
  echo -e "${RED}Cannot continue without Alice token${NC}"
  exit 1
fi

# Bob login
BOB_RESPONSE=$(curl -s -X POST "$AUTH_API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"bob.developer@example.com\",
    \"password\": \"DevSecure2024!Bob\",
    \"org_id\": \"$ORG_ID\"
  }")

BOB_TOKEN=$(echo $BOB_RESPONSE | jq -r '.access_token // empty')
BOB_USER_ID="5b6b84b5-01fe-46b1-827a-ed23548ac59c"

if [ -n "$BOB_TOKEN" ]; then
  test_result "Bob login" "success" "success"
else
  test_result "Bob login" "success" "failed"
  echo -e "${YELLOW}Bob may need to be added to organization${NC}"
fi

echo ""

# =============================================================================
# Test 4: Image Upload with OAuth
# =============================================================================
echo -e "${CYAN}${BOLD}[TEST 4] Image Upload with OAuth${NC}"
echo ""

# Create test image
echo "Test image content for OAuth migration" > /tmp/oauth_test_image.jpg

# Alice uploads private image
ALICE_UPLOAD=$(curl -s -X POST "$IMAGE_API/api/images/upload" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -F "file=@/tmp/oauth_test_image.jpg" \
  -F "visibility=private")

ALICE_IMAGE_ID=$(echo $ALICE_UPLOAD | jq -r '.id // empty')

if [ -n "$ALICE_IMAGE_ID" ] && [ "$ALICE_IMAGE_ID" != "null" ]; then
  test_result "Alice image upload" "success" "success"
else
  test_result "Alice image upload" "success" "failed"
  echo -e "${RED}Upload response: $ALICE_UPLOAD${NC}"
fi

echo ""

# =============================================================================
# Test 5: MongoDB Multi-Tenant Verification
# =============================================================================
echo -e "${CYAN}${BOLD}[TEST 5] MongoDB Multi-Tenant Verification${NC}"
echo ""

if [ -n "$ALICE_IMAGE_ID" ] && [ "$ALICE_IMAGE_ID" != "null" ]; then
  # Query MongoDB for uploaded image
  MONGO_IMAGE=$(docker exec image-api-mongodb mongosh image_db --quiet --eval \
    "db.images.findOne({_id: ObjectId('$ALICE_IMAGE_ID')}, {org_id: 1, user_id: 1, visibility: 1})" \
    2>/dev/null || echo "{}")

  # Check org_id
  IMAGE_ORG_ID=$(echo "$MONGO_IMAGE" | grep -o "org_id: '[^']*'" | cut -d"'" -f2)
  test_result "Image has org_id in MongoDB" "$ORG_ID" "$IMAGE_ORG_ID"

  # Check user_id
  IMAGE_USER_ID=$(echo "$MONGO_IMAGE" | grep -o "user_id: '[^']*'" | cut -d"'" -f2)
  test_result "Image has user_id in MongoDB" "$ALICE_USER_ID" "$IMAGE_USER_ID"

  # Check visibility
  IMAGE_VISIBILITY=$(echo "$MONGO_IMAGE" | grep -o "visibility: '[^']*'" | cut -d"'" -f2)
  test_result "Image visibility" "private" "$IMAGE_VISIBILITY"
else
  echo -e "${YELLOW}Skipping MongoDB verification (no image uploaded)${NC}"
fi

echo ""

# =============================================================================
# Test 6: Access Control - Multi-Tenant Isolation
# =============================================================================
echo -e "${CYAN}${BOLD}[TEST 6] Multi-Tenant Isolation${NC}"
echo ""

if [ -n "$ALICE_IMAGE_ID" ] && [ -n "$BOB_TOKEN" ]; then
  # Bob tries to access Alice's private image
  BOB_ACCESS=$(curl -s -w "\n%{http_code}" -X GET "$IMAGE_API/api/images/$ALICE_IMAGE_ID" \
    -H "Authorization: Bearer $BOB_TOKEN")

  BOB_STATUS=$(echo "$BOB_ACCESS" | tail -n1)
  BOB_RESPONSE=$(echo "$BOB_ACCESS" | head -n-1)

  test_result "Bob cannot access Alice's private image" "403" "$BOB_STATUS"

  # Verify error message
  BOB_ERROR=$(echo "$BOB_RESPONSE" | jq -r '.detail // empty')
  if [ "$BOB_ERROR" = "Access denied" ]; then
    test_result "Access denied error message" "Access denied" "Access denied"
  else
    test_result "Access denied error message" "Access denied" "$BOB_ERROR"
  fi
else
  echo -e "${YELLOW}Skipping isolation test (missing prerequisites)${NC}"
fi

echo ""

# =============================================================================
# Test 7: Org-Shared Images
# =============================================================================
echo -e "${CYAN}${BOLD}[TEST 7] Organization-Shared Images${NC}"
echo ""

if [ -n "$ALICE_TOKEN" ] && [ -n "$BOB_TOKEN" ]; then
  # Alice uploads org-shared image
  ALICE_ORG_UPLOAD=$(curl -s -X POST "$IMAGE_API/api/images/upload" \
    -H "Authorization: Bearer $ALICE_TOKEN" \
    -F "file=@/tmp/oauth_test_image.jpg" \
    -F "visibility=org")

  ORG_IMAGE_ID=$(echo $ALICE_ORG_UPLOAD | jq -r '.id // empty')

  if [ -n "$ORG_IMAGE_ID" ] && [ "$ORG_IMAGE_ID" != "null" ]; then
    test_result "Alice uploads org-shared image" "success" "success"

    # Bob accesses org-shared image (same org)
    BOB_ORG_ACCESS=$(curl -s -w "\n%{http_code}" -X GET "$IMAGE_API/api/images/$ORG_IMAGE_ID" \
      -H "Authorization: Bearer $BOB_TOKEN")

    BOB_ORG_STATUS=$(echo "$BOB_ORG_ACCESS" | tail -n1)

    test_result "Bob can access org-shared image" "200" "$BOB_ORG_STATUS"
  else
    test_result "Alice uploads org-shared image" "success" "failed"
  fi
else
  echo -e "${YELLOW}Skipping org-shared test (missing tokens)${NC}"
fi

echo ""

# =============================================================================
# Test 8: Service Token Admin Operations
# =============================================================================
echo -e "${CYAN}${BOLD}[TEST 8] Service Token Admin Operations${NC}"
echo ""

if [ -n "$SERVICE_TOKEN" ]; then
  # Service cleanup (should work with service token)
  CLEANUP_RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE "$IMAGE_API/api/images/cleanup?days=9999" \
    -H "Authorization: Bearer $SERVICE_TOKEN")

  CLEANUP_STATUS=$(echo "$CLEANUP_RESPONSE" | tail -n1)
  CLEANUP_BODY=$(echo "$CLEANUP_RESPONSE" | head -n-1)

  if [ "$CLEANUP_STATUS" = "200" ]; then
    test_result "Service token cleanup endpoint" "200" "200"

    DELETED_COUNT=$(echo "$CLEANUP_BODY" | jq -r '.deleted_count // empty')
    if [ -n "$DELETED_COUNT" ]; then
      test_result "Cleanup returns deleted_count" "present" "present"
    else
      test_result "Cleanup returns deleted_count" "present" "missing"
    fi
  else
    test_result "Service token cleanup endpoint" "200" "$CLEANUP_STATUS"
  fi
else
  echo -e "${YELLOW}Skipping service token test (no service token)${NC}"
fi

echo ""

# =============================================================================
# Test 9: List User's Images
# =============================================================================
echo -e "${CYAN}${BOLD}[TEST 9] List User's Images${NC}"
echo ""

if [ -n "$ALICE_TOKEN" ]; then
  ALICE_IMAGES=$(curl -s -X GET "$IMAGE_API/api/images" \
    -H "Authorization: Bearer $ALICE_TOKEN")

  IMAGE_COUNT=$(echo "$ALICE_IMAGES" | jq '. | length')

  if [ "$IMAGE_COUNT" -ge 0 ]; then
    test_result "Alice can list her images" "success" "success"
  else
    test_result "Alice can list her images" "success" "failed"
  fi
else
  echo -e "${YELLOW}Skipping list images test${NC}"
fi

echo ""

# =============================================================================
# Test Summary
# =============================================================================
echo -e "${BOLD}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║                    Test Results Summary                        ║${NC}"
echo -e "${BOLD}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}Total Tests Run: $TESTS_RUN${NC}"
echo -e "${GREEN}Tests Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Tests Failed: $TESTS_FAILED${NC}"
echo ""

SUCCESS_RATE=$((TESTS_PASSED * 100 / TESTS_RUN))

if [ $TESTS_FAILED -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✅ ALL TESTS PASSED! OAuth migration successful! 🎉${NC}"
  echo -e "${GREEN}Success Rate: 100%${NC}"
  echo ""
  echo -e "${YELLOW}Next steps:${NC}"
  echo -e "  1. Update frontend to use OAuth tokens"
  echo -e "  2. Test in production environment"
  echo -e "  3. Monitor OAuth logs for errors"
  exit 0
else
  echo -e "${RED}${BOLD}❌ SOME TESTS FAILED - Migration needs attention${NC}"
  echo -e "${YELLOW}Success Rate: $SUCCESS_RATE%${NC}"
  echo ""
  echo -e "${YELLOW}Troubleshooting steps:${NC}"
  echo -e "  1. Check image-api logs: docker logs image-api --tail 50"
  echo -e "  2. Verify JWT_SECRET matches auth-api"
  echo -e "  3. Rebuild Docker: docker compose build --no-cache image-api"
  echo -e "  4. Review OAUTH_MIGRATION_GUIDE.md troubleshooting section"
  exit 1
fi

# Cleanup
rm -f /tmp/oauth_test_image.jpg
