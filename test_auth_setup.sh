#!/bin/bash
# =============================================================================
# Authorization Testing Infrastructure Setup
# =============================================================================
# Starts all required services for authorization E2E testing:
# - Redis (caching + circuit breaker state)
# - PostgreSQL (auth-api database)
# - Auth-API (permission verification)
# - Image-API (service under test)
# =============================================================================

set -euo pipefail

# Source utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/test_auth_utils.sh"

# Configuration
readonly IMAGE_API_URL="http://localhost:8009"
readonly AUTH_API_URL="http://localhost:8000"
readonly REDIS_PORT="6379"
readonly POSTGRES_PORT="5441"

# =============================================================================
# Main Setup Flow
# =============================================================================

main() {
    print_header "Authorization Testing Infrastructure Setup"

    # Step 1: Check if infrastructure is already running
    print_section "Checking Existing Services"
    check_existing_services

    # Step 2: Start Redis (required for image-api)
    print_section "Starting Redis"
    start_redis

    # Step 3: Start PostgreSQL (required for auth-api)
    print_section "Starting PostgreSQL"
    start_postgres

    # Step 4: Start Auth-API
    print_section "Starting Auth-API"
    start_auth_api

    # Step 5: Start Image-API
    print_section "Starting Image-API"
    start_image_api

    # Step 6: Verify all services are healthy
    print_section "Health Checks"
    verify_all_services

    # Step 7: Clean cache and circuit breaker
    print_section "Initial Cleanup"
    clear_auth_cache
    reset_circuit_breaker

    print_header "Infrastructure Ready ✅"
    print_info "Services available:"
    echo "  - Image-API: $IMAGE_API_URL"
    echo "  - Auth-API:  $AUTH_API_URL"
    echo "  - Redis:     localhost:$REDIS_PORT"
    echo "  - PostgreSQL: localhost:$POSTGRES_PORT"
    echo ""
    print_info "Next steps:"
    echo "  1. Run ./test_auth_data.sh to create test users and groups"
    echo "  2. Run ./generate_test_tokens.sh to generate JWT tokens"
    echo "  3. Run ./test_auth_e2e.sh to execute test suite"
}

# =============================================================================
# Service Startup Functions
# =============================================================================

check_existing_services() {
    local all_running=true

    # Check if image-api is running
    if docker ps --format '{{.Names}}' | grep -q "image-processor-api"; then
        print_info "Image-API already running"
    else
        all_running=false
    fi

    # Check if auth-api is running
    if docker ps --format '{{.Names}}' | grep -q "auth-api"; then
        print_info "Auth-API already running"
    else
        all_running=false
    fi

    # Check if Redis is running
    if docker ps --format '{{.Names}}' | grep -q "image-processor-redis"; then
        print_info "Redis already running"
    else
        all_running=false
    fi

    # Check if PostgreSQL is running
    if docker ps --format '{{.Names}}' | grep -q "activity-postgres-db"; then
        print_info "PostgreSQL already running"
    else
        all_running=false
    fi

    if $all_running; then
        print_warning "All services already running. To restart, run: docker compose down && ./test_auth_setup.sh"
    fi
}

start_redis() {
    if docker ps --format '{{.Names}}' | grep -q "image-processor-redis"; then
        print_success "Redis already running"
        return 0
    fi

    print_info "Starting Redis container..."
    cd "$SCRIPT_DIR"
    docker compose up -d redis

    wait_for_service "Redis" "redis://localhost:$REDIS_PORT" 30 2

    # Test Redis connection
    if redis_exec "PING" | grep -q "PONG"; then
        print_success "Redis responding to PING"
    else
        print_error "Redis not responding"
        return 1
    fi
}

start_postgres() {
    if docker ps --format '{{.Names}}' | grep -q "activity-postgres-db"; then
        print_success "PostgreSQL already running"
        return 0
    fi

    print_info "Starting PostgreSQL from infrastructure..."
    cd "$SCRIPT_DIR/../scripts"

    if [[ -f "./start-infra.sh" ]]; then
        ./start-infra.sh
    else
        print_error "Infrastructure startup script not found"
        return 1
    fi

    # Wait for PostgreSQL to be ready
    sleep 5

    # Test PostgreSQL connection
    if docker exec activity-postgres-db pg_isready -U postgres > /dev/null 2>&1; then
        print_success "PostgreSQL ready"
    else
        print_error "PostgreSQL not ready"
        return 1
    fi
}

start_auth_api() {
    if docker ps --format '{{.Names}}' | grep -q "auth-api"; then
        print_success "Auth-API already running"
        return 0
    fi

    print_info "Starting Auth-API..."
    cd "$SCRIPT_DIR/../auth-api"

    # Start auth-api with docker compose
    docker compose up -d

    # Wait for health endpoint
    wait_for_service "Auth-API" "$AUTH_API_URL/health" 60 3

    # Verify database connection
    local health_response=$(curl -s "$AUTH_API_URL/health")
    if echo "$health_response" | grep -q "healthy"; then
        print_success "Auth-API healthy and connected to database"
    else
        print_warning "Auth-API started but health check returned unexpected response"
        echo "$health_response"
    fi
}

start_image_api() {
    if docker ps --format '{{.Names}}' | grep -q "image-processor-api"; then
        print_success "Image-API already running"
        return 0
    fi

    print_info "Starting Image-API..."
    cd "$SCRIPT_DIR"

    # Build and start image-api
    docker compose build --no-cache api
    docker compose up -d api worker

    # Wait for health endpoint
    wait_for_service "Image-API" "$IMAGE_API_URL/api/v1/health" 60 3

    # Verify Redis connection from image-api
    local health_response=$(curl -s "$IMAGE_API_URL/api/v1/health")
    if echo "$health_response" | grep -q "healthy"; then
        print_success "Image-API healthy and connected to Redis"
    else
        print_warning "Image-API started but health check returned unexpected response"
        echo "$health_response"
    fi
}

# =============================================================================
# Verification Functions
# =============================================================================

verify_all_services() {
    local all_healthy=true

    # Check Image-API
    if ! check_service_health "Image-API" "$IMAGE_API_URL/api/v1/health"; then
        all_healthy=false
    fi

    # Check Auth-API
    if ! check_service_health "Auth-API" "$AUTH_API_URL/health"; then
        all_healthy=false
    fi

    # Check Redis
    if ! redis_exec "PING" | grep -q "PONG"; then
        print_error "Redis: unhealthy"
        all_healthy=false
    else
        print_success "Redis: healthy"
    fi

    # Check PostgreSQL
    if docker exec activity-postgres-db pg_isready -U postgres > /dev/null 2>&1; then
        print_success "PostgreSQL: healthy"
    else
        print_error "PostgreSQL: unhealthy"
        all_healthy=false
    fi

    # Check Docker containers
    check_docker_service "image-processor-api" || all_healthy=false
    check_docker_service "image-processor-redis" || all_healthy=false
    check_docker_service "auth-api" || all_healthy=false
    check_docker_service "activity-postgres-db" || all_healthy=false

    if ! $all_healthy; then
        print_error "Some services are unhealthy"
        return 1
    fi

    print_success "All services healthy ✅"
}

# =============================================================================
# Entry Point
# =============================================================================

main "$@"
