#!/bin/bash
# Rebuild script for image-api
# Steps:
# 1. Stop all containers
# 2. Remove image-api images (NOT volumes!)
# 3. Rebuild and start
# 4. Show running containers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Image-API Rebuild Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Stop all containers
echo -e "${YELLOW}Step 1: Stopping all containers...${NC}"
docker compose down
echo -e "${GREEN}✅ Containers stopped${NC}"
echo ""

# Step 2: Remove image-api images (NOT volumes!)
echo -e "${YELLOW}Step 2: Removing image-api images...${NC}"
# Get image names for this project
IMAGE_NAMES=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "image-api" || true)

if [ -n "$IMAGE_NAMES" ]; then
    echo "Found images to remove:"
    echo "$IMAGE_NAMES"
    echo ""

    # Remove each image
    for img in $IMAGE_NAMES; do
        echo "Removing $img..."
        docker rmi "$img" 2>/dev/null || echo "  (already removed)"
    done
    echo -e "${GREEN}✅ Images removed${NC}"
else
    echo "No image-api images found to remove"
    echo -e "${GREEN}✅ No images to remove${NC}"
fi
echo ""

# Step 3: Rebuild and start
echo -e "${YELLOW}Step 3: Building and starting services...${NC}"
echo "This may take a few minutes..."
echo ""
docker compose build --no-cache image-api
echo ""
docker compose up -d
echo ""
echo -e "${GREEN}✅ Services started${NC}"
echo ""

# Wait a moment for containers to stabilize
echo "Waiting 3 seconds for containers to stabilize..."
sleep 3
echo ""

# Step 4: Show running containers
echo -e "${YELLOW}Step 4: Running containers:${NC}"
echo ""
docker compose ps
echo ""

# Show image-api logs (last 10 lines)
echo -e "${YELLOW}Image-API Logs (last 10 lines):${NC}"
echo ""
docker compose logs --tail 10 image-api
echo ""

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ Rebuild complete!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f image-api    # Follow logs"
echo "  docker compose ps                   # Check status"
echo "  curl http://localhost:8009/health   # Test API health"
echo "  curl http://localhost:8009/dashboard # Technical dashboard"
echo ""
