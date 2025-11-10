#!/bin/bash
# Observability Stack Integration Verification Script
# Run this after starting the image-api services

set -e

echo "========================================="
echo "Image API Observability Integration Test"
echo "========================================="
echo ""

SERVICE_URL="http://localhost:8004"
PROMETHEUS_URL="http://localhost:9091"
LOKI_URL="http://localhost:3100"
GRAFANA_URL="http://localhost:3002"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

success() {
    echo -e "${GREEN}✓${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

heading() {
    echo ""
    echo -e "${YELLOW}===${NC} $1"
    echo ""
}

# 1. Test Service Health
heading "1. Testing Service Health"
if curl -s -f "${SERVICE_URL}/api/v1/health" > /dev/null; then
    success "Service is healthy"
    curl -s "${SERVICE_URL}/api/v1/health" | jq .
else
    error "Service health check failed"
    exit 1
fi

# 2. Test Metrics Endpoint
heading "2. Testing Prometheus Metrics Endpoint"
if curl -s -f "${SERVICE_URL}/metrics" > /dev/null; then
    success "Metrics endpoint is accessible"
    echo "Sample metrics:"
    curl -s "${SERVICE_URL}/metrics" | grep "^# HELP" | head -10
else
    error "Metrics endpoint failed"
    exit 1
fi

# 3. Test Trace ID in Response Headers
heading "3. Testing Trace ID Propagation"
TRACE_RESPONSE=$(curl -s -D - "${SERVICE_URL}/api/v1/health" 2>&1)
if echo "$TRACE_RESPONSE" | grep -i "x-trace-id" > /dev/null; then
    TRACE_ID=$(echo "$TRACE_RESPONSE" | grep -i "x-trace-id" | awk '{print $2}' | tr -d '\r')
    success "X-Trace-ID header present: $TRACE_ID"
else
    error "X-Trace-ID header missing"
fi

if echo "$TRACE_RESPONSE" | grep -i "x-correlation-id" > /dev/null; then
    success "X-Correlation-ID header present (backward compatibility)"
else
    warning "X-Correlation-ID header missing"
fi

# 4. Test Custom Trace ID Propagation
heading "4. Testing Custom Trace ID Propagation"
CUSTOM_TRACE="test-trace-$(date +%s)"
CUSTOM_RESPONSE=$(curl -s -H "X-Trace-ID: $CUSTOM_TRACE" -D - "${SERVICE_URL}/api/v1/health" 2>&1)
if echo "$CUSTOM_RESPONSE" | grep "$CUSTOM_TRACE" > /dev/null; then
    success "Custom trace ID propagated correctly: $CUSTOM_TRACE"
else
    error "Custom trace ID not propagated"
fi

# 5. Make Some Test Requests to Generate Metrics
heading "5. Generating Test Traffic for Metrics"
echo "Making 10 test requests..."
for i in {1..10}; do
    curl -s "${SERVICE_URL}/api/v1/health" > /dev/null
    echo -n "."
done
echo ""
success "Test traffic generated"

# 6. Verify Prometheus Metrics Content
heading "6. Verifying Prometheus Metrics Content"

# Check for HTTP metrics
if curl -s "${SERVICE_URL}/metrics" | grep -q "http_requests_total"; then
    success "http_requests_total metric present"
else
    error "http_requests_total metric missing"
fi

if curl -s "${SERVICE_URL}/metrics" | grep -q "http_request_duration_seconds"; then
    success "http_request_duration_seconds metric present"
else
    error "http_request_duration_seconds metric missing"
fi

if curl -s "${SERVICE_URL}/metrics" | grep -q "http_requests_in_progress"; then
    success "http_requests_in_progress metric present"
else
    error "http_requests_in_progress metric missing"
fi

# Check for service info
if curl -s "${SERVICE_URL}/metrics" | grep -q "service_info"; then
    success "service_info metric present"
else
    error "service_info metric missing"
fi

# 7. Wait for Service Discovery
heading "7. Waiting for Prometheus Service Discovery (30 seconds)"
echo "Prometheus scrapes services every 15 seconds..."
sleep 5
echo "25 seconds remaining..."
sleep 5
echo "20 seconds remaining..."
sleep 5
echo "15 seconds remaining..."
sleep 5
echo "10 seconds remaining..."
sleep 5
echo "5 seconds remaining..."
sleep 5
success "Service discovery window completed"

# 8. Check Prometheus Targets
heading "8. Checking Prometheus Auto-Discovery"
if curl -s "${PROMETHEUS_URL}/api/v1/targets" | jq -e '.data.activeTargets[] | select(.labels.job=="docker-services") | select(.labels.container_name=="image-processor-api")' > /dev/null 2>&1; then
    success "Service discovered by Prometheus"
    echo "Target details:"
    curl -s "${PROMETHEUS_URL}/api/v1/targets" | jq '.data.activeTargets[] | select(.labels.container_name=="image-processor-api") | {health: .health, scrapeUrl: .scrapeUrl, lastScrape: .lastScrape}'
else
    warning "Service not yet discovered by Prometheus (may need more time)"
    echo "Checking all targets:"
    curl -s "${PROMETHEUS_URL}/api/v1/targets" | jq '.data.activeTargets[] | select(.labels.job=="docker-services") | .labels.container_name'
fi

# 9. Query Prometheus for Metrics
heading "9. Querying Prometheus for Image API Metrics"
QUERY='up{service="image-processor"}'
if curl -s -G "${PROMETHEUS_URL}/api/v1/query" --data-urlencode "query=${QUERY}" | jq -e '.data.result[] | select(.value[1]=="1")' > /dev/null 2>&1; then
    success "Service is UP in Prometheus"
    curl -s -G "${PROMETHEUS_URL}/api/v1/query" --data-urlencode "query=${QUERY}" | jq '.data.result[]'
else
    warning "Service metrics not yet in Prometheus (scraping may not have occurred yet)"
fi

# 10. Check Loki for Logs
heading "10. Checking Loki for Image API Logs"
START_TIME=$(($(date +%s) - 300))000000000  # Last 5 minutes
END_TIME=$(date +%s)000000000

LOKI_QUERY=$(curl -G -s "${LOKI_URL}/loki/api/v1/query_range" \
  --data-urlencode 'query={container_name="image-processor-api"}' \
  --data-urlencode "start=${START_TIME}" \
  --data-urlencode "end=${END_TIME}" \
  --data-urlencode 'limit=5')

if echo "$LOKI_QUERY" | jq -e '.data.result[0].values[0][1]' > /dev/null 2>&1; then
    success "Logs found in Loki"
    echo "Sample log entries:"
    echo "$LOKI_QUERY" | jq -r '.data.result[0].values[][1]' | head -3 | jq .
else
    warning "No logs found in Loki yet (may need more time for collection)"
fi

# 11. Verify Log Format
heading "11. Verifying JSON Log Format"
echo "Checking container logs for JSON structure..."
LOG_SAMPLE=$(docker logs image-processor-api 2>&1 | grep -v "^WARNING" | grep "{" | tail -1)
if echo "$LOG_SAMPLE" | jq . > /dev/null 2>&1; then
    success "Logs are valid JSON"
    echo "Sample log entry:"
    echo "$LOG_SAMPLE" | jq .

    # Check for required fields
    if echo "$LOG_SAMPLE" | jq -e '.trace_id' > /dev/null 2>&1; then
        success "trace_id field present in logs"
    else
        warning "trace_id field missing in logs"
    fi

    if echo "$LOG_SAMPLE" | jq -e '.service' > /dev/null 2>&1; then
        success "service field present in logs"
    else
        warning "service field missing in logs"
    fi

    if echo "$LOG_SAMPLE" | jq -e '.timestamp' > /dev/null 2>&1; then
        success "timestamp field present in logs"
    else
        warning "timestamp field missing in logs"
    fi
else
    error "Logs are not valid JSON"
fi

# 12. Check Docker Labels
heading "12. Verifying Docker Labels"
if docker inspect image-processor-api | jq -e '.[] | .Config.Labels | select(."prometheus.scrape" == "true")' > /dev/null 2>&1; then
    success "Prometheus labels configured correctly"
else
    error "Prometheus labels missing or incorrect"
fi

if docker inspect image-processor-api | jq -e '.[] | .Config.Labels | select(."loki.collect" == "true")' > /dev/null 2>&1; then
    success "Loki labels configured correctly"
else
    error "Loki labels missing or incorrect"
fi

# 13. Check Network Configuration
heading "13. Verifying Network Configuration"
if docker inspect image-processor-api | jq -e '.[] | .NetworkSettings.Networks["activity-observability"]' > /dev/null 2>&1; then
    success "Connected to activity-observability network"
else
    error "Not connected to activity-observability network"
fi

# 14. Final Summary
heading "Summary"
echo ""
echo "Grafana Dashboards:"
echo "  Service Overview: ${GRAFANA_URL}/d/service-overview"
echo "  Logs Explorer:    ${GRAFANA_URL}/d/logs-explorer"
echo "  API Performance:  ${GRAFANA_URL}/d/api-performance"
echo ""
echo "Direct Access:"
echo "  Prometheus:       ${PROMETHEUS_URL}"
echo "  Loki:            ${LOKI_URL}"
echo "  Image API:       ${SERVICE_URL}"
echo "  Metrics:         ${SERVICE_URL}/metrics"
echo "  Health:          ${SERVICE_URL}/api/v1/health"
echo ""
echo "Next Steps:"
echo "1. Open Grafana and check 'Service Overview' dashboard"
echo "2. Verify 'image-processor' appears in the service list"
echo "3. Check logs in 'Logs Explorer' with query: {service=\"image-processor\"}"
echo "4. Generate traffic: curl ${SERVICE_URL}/api/v1/health"
echo "5. Watch metrics update in Grafana dashboards"
echo ""
success "Verification complete!"
