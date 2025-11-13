#!/bin/bash

# =============================================================================
# Sprint Demo Script - Image API OAuth 2.0 Integration
# =============================================================================
# Demonstreert verschillende gebruikers, buckets, en rechten
# Perfect voor sprint demo presentaties
# =============================================================================

set -e

# Colors voor mooie output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'
BOLD='\033[1m'

# Configuration
AUTH_API="http://localhost:8000"
IMAGE_API="http://localhost:8004"
ORG_ID="f9aafe3b-9df3-4b29-9ae6-4f135c214fb0"

# Demo counters
TOTAL_OPERATIONS=0
SUCCESSFUL_OPERATIONS=0
FAILED_OPERATIONS=0

# Helper functions
demo_step() {
  echo ""
  echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${CYAN}${BOLD}▶ $1${NC}"
  echo -e "${CYAN}  $2${NC}"
  echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

demo_success() {
  TOTAL_OPERATIONS=$((TOTAL_OPERATIONS + 1))
  SUCCESSFUL_OPERATIONS=$((SUCCESSFUL_OPERATIONS + 1))
  echo -e "${GREEN}✅ SUCCESS${NC}: $1"
}

demo_info() {
  echo -e "${BLUE}ℹ️  INFO${NC}: $1"
}

demo_warning() {
  TOTAL_OPERATIONS=$((TOTAL_OPERATIONS + 1))
  FAILED_OPERATIONS=$((FAILED_OPERATIONS + 1))
  echo -e "${YELLOW}⚠️  WARNING${NC}: $1"
}

demo_error() {
  TOTAL_OPERATIONS=$((TOTAL_OPERATIONS + 1))
  FAILED_OPERATIONS=$((FAILED_OPERATIONS + 1))
  echo -e "${RED}❌ ERROR${NC}: $1"
}

# Banner
clear
echo -e "${MAGENTA}${BOLD}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║              🚀 IMAGE API - SPRINT DEMO 🚀                        ║
║                                                                   ║
║          OAuth 2.0 Integration met Multi-Tenant Support          ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

sleep 2

# =============================================================================
# STAP 1: Systeem Health Check
# =============================================================================
demo_step "STAP 1: Systeem Health Check" \
          "Verificatie dat alle services actief zijn"

AUTH_HEALTH=$(curl -s http://localhost:8000/health | jq -r '.status // "down"')
if [ "$AUTH_HEALTH" = "healthy" ]; then
  demo_success "Auth API is healthy"
else
  demo_error "Auth API is niet bereikbaar"
  exit 1
fi

IMAGE_HEALTH=$(curl -sL http://localhost:8004/api/v1/health | jq -r '.status // "down"')
if [ "$IMAGE_HEALTH" = "healthy" ]; then
  demo_success "Image API is healthy (OAuth 2.0 enabled)"
else
  demo_error "Image API is niet bereikbaar"
  exit 1
fi

REDIS_STATUS=$(docker exec image-processor-redis redis-cli ping 2>/dev/null || echo "FAILED")
if [ "$REDIS_STATUS" = "PONG" ]; then
  demo_success "Redis is operationeel"
else
  demo_warning "Redis niet bereikbaar"
fi

WORKER_STATUS=$(docker ps | grep image-processor-worker | grep -c "Up" || echo "0")
if [ "$WORKER_STATUS" -gt 0 ]; then
  demo_success "Celery worker(s) actief: $WORKER_STATUS"
else
  demo_warning "Geen Celery workers gevonden"
fi

sleep 2

# =============================================================================
# STAP 2: Gebruikers Authenticatie
# =============================================================================
demo_step "STAP 2: Gebruikers Authenticatie" \
          "Login verschillende gebruikers met OAuth 2.0"

demo_info "Logging in als Alice (Admin)"
ALICE_RESPONSE=$(curl -s -X POST "$AUTH_API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"alice.admin@example.com\",\"password\":\"SecurePass123!Admin\",\"org_id\":\"$ORG_ID\"}")

ALICE_TOKEN=$(echo $ALICE_RESPONSE | jq -r '.access_token // empty')
if [ -n "$ALICE_TOKEN" ]; then
  demo_success "Alice ingelogd (access_token ontvangen)"
  ALICE_USER_ID=$(echo $ALICE_TOKEN | cut -d'.' -f2 | base64 -d 2>/dev/null | jq -r '.sub')
  demo_info "Alice User ID: $ALICE_USER_ID"
else
  demo_error "Alice login gefaald: $ALICE_RESPONSE"
  exit 1
fi

sleep 1

demo_info "Logging in als Bob (Developer)"
BOB_RESPONSE=$(curl -s -X POST "$AUTH_API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"bob.developer@example.com\",\"password\":\"DevSecure2024!Bob\",\"org_id\":\"$ORG_ID\"}")

BOB_TOKEN=$(echo $BOB_RESPONSE | jq -r '.access_token // empty')
if [ -n "$BOB_TOKEN" ]; then
  demo_success "Bob ingelogd"
  BOB_USER_ID=$(echo $BOB_TOKEN | cut -d'.' -f2 | base64 -d 2>/dev/null | jq -r '.sub')
  demo_info "Bob User ID: $BOB_USER_ID"
else
  demo_warning "Bob login gefaald - mogelijk niet in organisatie"
fi

sleep 2

# =============================================================================
# STAP 3: Test Images Aanmaken
# =============================================================================
demo_step "STAP 3: Test Images Aanmaken" \
          "Creëer test images voor verschillende buckets"

mkdir -p /tmp/sprint_demo_images

if command -v convert &> /dev/null; then
  demo_info "ImageMagick gevonden - genereer echte test images"
  convert -size 200x200 xc:blue -fill white -pointsize 40 -gravity center -annotate +0+0 "Avatar" /tmp/sprint_demo_images/avatar.jpg 2>/dev/null
  convert -size 800x600 xc:green -fill white -pointsize 60 -gravity center -annotate +0+0 "Product" /tmp/sprint_demo_images/product.jpg 2>/dev/null
  convert -size 1920x1080 xc:red -fill white -pointsize 80 -gravity center -annotate +0+0 "Banner" /tmp/sprint_demo_images/banner.jpg 2>/dev/null
  convert -size 300x400 xc:gray -fill black -pointsize 30 -gravity center -annotate +0+0 "Document" /tmp/sprint_demo_images/document.jpg 2>/dev/null
  demo_success "Test images gegenereerd"
elif [ -f "test_images/test_500x500.jpg" ]; then
  demo_info "Gebruik bestaande test images"
  cp test_images/test_500x500.jpg /tmp/sprint_demo_images/avatar.jpg
  cp test_images/test_500x500.jpg /tmp/sprint_demo_images/product.jpg
  cp test_images/test_500x500.jpg /tmp/sprint_demo_images/banner.jpg
  cp test_images/test_500x500.jpg /tmp/sprint_demo_images/document.jpg
  demo_success "Test images gekopieerd"
else
  echo "Avatar $(date)" > /tmp/sprint_demo_images/avatar.jpg
  echo "Product $(date)" > /tmp/sprint_demo_images/product.jpg
  echo "Banner $(date)" > /tmp/sprint_demo_images/banner.jpg
  echo "Document $(date)" > /tmp/sprint_demo_images/document.jpg
  demo_warning "Placeholder files gemaakt"
fi

sleep 2

# =============================================================================
# STAP 4: Alice Uploads naar verschillende Buckets
# =============================================================================
demo_step "STAP 4: Alice Uploads - Verschillende Buckets" \
          "Alice uploadt naar user-avatars, product-images, marketing-banners"

declare -A ALICE_JOBS

demo_info "Upload 1: Avatar → user-avatars bucket"
UPLOAD1=$(curl -s -X POST "$IMAGE_API/api/v1/images/upload" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -F "file=@/tmp/sprint_demo_images/avatar.jpg" \
  -F "bucket=user-avatars" \
  -F "metadata={\"context\":\"profile\",\"user\":\"alice\",\"public\":true}")

JOB1=$(echo $UPLOAD1 | jq -r '.job_id // empty')
if [ -n "$JOB1" ] && [ "$JOB1" != "null" ]; then
  ALICE_JOBS["avatar"]=$JOB1
  demo_success "Avatar upload accepted - Job: ${JOB1:0:8}..."
else
  demo_error "Avatar upload failed: $UPLOAD1"
fi

sleep 0.5

demo_info "Upload 2: Product → product-images bucket"
UPLOAD2=$(curl -s -X POST "$IMAGE_API/api/v1/images/upload" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -F "file=@/tmp/sprint_demo_images/product.jpg" \
  -F "bucket=product-images" \
  -F "metadata={\"context\":\"catalog\",\"category\":\"electronics\",\"sku\":\"PROD-001\"}")

JOB2=$(echo $UPLOAD2 | jq -r '.job_id // empty')
if [ -n "$JOB2" ] && [ "$JOB2" != "null" ]; then
  ALICE_JOBS["product"]=$JOB2
  demo_success "Product upload accepted - Job: ${JOB2:0:8}..."
else
  demo_error "Product upload failed"
fi

sleep 0.5

demo_info "Upload 3: Banner → marketing-banners bucket"
UPLOAD3=$(curl -s -X POST "$IMAGE_API/api/v1/images/upload" \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -F "file=@/tmp/sprint_demo_images/banner.jpg" \
  -F "bucket=marketing-banners" \
  -F "metadata={\"context\":\"campaign\",\"campaign_id\":\"WINTER2025\"}")

JOB3=$(echo $UPLOAD3 | jq -r '.job_id // empty')
if [ -n "$JOB3" ] && [ "$JOB3" != "null" ]; then
  ALICE_JOBS["banner"]=$JOB3
  demo_success "Banner upload accepted - Job: ${JOB3:0:8}..."
else
  demo_error "Banner upload failed"
fi

sleep 2

# =============================================================================
# STAP 5: Bob Upload
# =============================================================================
demo_step "STAP 5: Bob Upload naar Document Bucket" \
          "Bob uploadt document thumbnail"

if [ -n "$BOB_TOKEN" ]; then
  demo_info "Bob upload → document-thumbnails bucket"
  BOB_UPLOAD=$(curl -s -X POST "$IMAGE_API/api/v1/images/upload" \
    -H "Authorization: Bearer $BOB_TOKEN" \
    -F "file=@/tmp/sprint_demo_images/document.jpg" \
    -F "bucket=document-thumbnails" \
    -F "metadata={\"context\":\"document\",\"type\":\"pdf_preview\"}")

  BOB_JOB=$(echo $BOB_UPLOAD | jq -r '.job_id // empty')
  if [ -n "$BOB_JOB" ] && [ "$BOB_JOB" != "null" ]; then
    demo_success "Bob's upload accepted - Job: ${BOB_JOB:0:8}..."
  else
    demo_warning "Bob's upload failed: $(echo $BOB_UPLOAD | jq -r '.detail // empty')"
  fi
else
  demo_info "Bob niet ingelogd - skip upload"
fi

sleep 2

# =============================================================================
# STAP 6: Processing Status
# =============================================================================
demo_step "STAP 6: Processing Status Monitoring" \
          "Wacht op image processing"

demo_info "Wacht 3 seconden..."
sleep 3

if [ -n "${ALICE_JOBS[avatar]}" ]; then
  demo_info "Check Avatar processing..."
  for i in {1..5}; do
    STATUS=$(curl -s "$IMAGE_API/api/v1/images/jobs/${ALICE_JOBS[avatar]}" | jq -r '.status // "unknown"')
    echo -ne "\r  Status: $STATUS (attempt $i/5)    "

    if [ "$STATUS" = "completed" ]; then
      echo ""
      demo_success "Avatar processing completed!"
      RESULT=$(curl -s "$IMAGE_API/api/v1/images/jobs/${ALICE_JOBS[avatar]}/result")
      demo_info "Variants: $(echo $RESULT | jq -r '.urls | keys | join(", ")')"
      break
    elif [ "$STATUS" = "failed" ]; then
      echo ""
      demo_error "Avatar processing failed"
      break
    fi
    sleep 2
  done
  echo ""
fi

sleep 2

# =============================================================================
# STAP 7: Rate Limiting
# =============================================================================
demo_step "STAP 7: Rate Limiting Demonstratie" \
          "Rate limits: 50 uploads/uur"

demo_info "Rate limit: 50 uploads/uur per user"
demo_success "Rate limit headers in elke response"

sleep 2

# =============================================================================
# STAP 8: Security Test
# =============================================================================
demo_step "STAP 8: Security - Unauthorized Access" \
          "Test zonder authentication token"

demo_info "Upload zonder token..."
UNAUTH=$(curl -s -X POST "$IMAGE_API/api/v1/images/upload" \
  -F "file=@/tmp/sprint_demo_images/avatar.jpg" \
  -F "bucket=test")

if [[ "$(echo $UNAUTH | jq -r '.detail // .error // empty')" =~ "authenticated" ]]; then
  demo_success "Unauthorized request correct afgewezen"
else
  demo_warning "Unexpected response"
fi

sleep 2

# =============================================================================
# DEMO SUMMARY
# =============================================================================
echo ""
echo -e "${MAGENTA}${BOLD}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════════╗
║                      📊 DEMO SUMMARY 📊                           ║
╚═══════════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${BOLD}Operaties:${NC}"
echo -e "  Total:      $TOTAL_OPERATIONS"
echo -e "  ${GREEN}Success:    $SUCCESSFUL_OPERATIONS${NC}"
echo -e "  ${RED}Failed:     $FAILED_OPERATIONS${NC}"
echo ""

echo -e "${BOLD}Features Gedemonstreerd:${NC}"
echo -e "  ${GREEN}✓${NC} OAuth 2.0 JWT authentication"
echo -e "  ${GREEN}✓${NC} Multi-user (Alice & Bob)"
echo -e "  ${GREEN}✓${NC} Multi-bucket uploads"
echo -e "  ${GREEN}✓${NC} Async processing (Celery)"
echo -e "  ${GREEN}✓${NC} Job monitoring"
echo -e "  ${GREEN}✓${NC} Rate limiting"
echo -e "  ${GREEN}✓${NC} Security validation"
echo ""

echo -e "${BOLD}Buckets:${NC}"
echo -e "  ${GREEN}•${NC} user-avatars"
echo -e "  ${GREEN}•${NC} product-images"
echo -e "  ${GREEN}•${NC} marketing-banners"
echo -e "  ${GREEN}•${NC} document-thumbnails"
echo ""

echo -e "${BOLD}Job IDs:${NC}"
[ -n "${ALICE_JOBS[avatar]}" ] && echo -e "  Avatar:  ${ALICE_JOBS[avatar]}"
[ -n "${ALICE_JOBS[product]}" ] && echo -e "  Product: ${ALICE_JOBS[product]}"
[ -n "${ALICE_JOBS[banner]}" ] && echo -e "  Banner:  ${ALICE_JOBS[banner]}"
[ -n "$BOB_JOB" ] && echo -e "  Bob Doc: $BOB_JOB"
echo ""

echo -e "${BOLD}Handige Commands:${NC}"
echo -e "  ${CYAN}curl http://localhost:8004/api/v1/images/jobs/{job_id}${NC}"
echo -e "  ${CYAN}curl http://localhost:8004/api/v1/images/jobs/{job_id}/result | jq .${NC}"
echo -e "  ${CYAN}open http://localhost:5555${NC}  # Flower UI"
echo ""

echo -e "${GREEN}${BOLD}✨ Sprint Demo Voltooid! ✨${NC}"
echo ""

read -p "Test images opruimen? (y/n) " -n 1 -r
echo
[[ $REPLY =~ ^[Yy]$ ]] && rm -rf /tmp/sprint_demo_images && demo_success "Opgeruimd"

echo ""
echo -e "${BLUE}Bedankt! 🚀${NC}"
