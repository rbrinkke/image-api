"""
Webhook Receiver Mock
=====================

Mock webhook receiver for testing event notifications.
Logs and validates webhook events, supports HMAC signature verification.

Usage:
    python webhook_receiver_mock.py
    # or
    uvicorn webhook_receiver_mock:app --reload --port 4000

Endpoints:
    POST /webhooks/{client_id}        - Receive webhook event
    GET /webhooks/events              - List all received events
    GET /webhooks/events/{event_id}   - Get specific event details
    DELETE /webhooks/events           - Clear all events
    POST /webhooks/replay/{event_id}  - Replay event to another URL
    GET /webhooks/stats               - Get webhook statistics
    GET /health                       - Health check

Configuration:
    WEBHOOK_SECRET: Secret key for HMAC verification (default: webhook-secret-123)
    PORT: Server port (default: 4000)
"""

from fastapi import FastAPI, Request, HTTPException, Path, Query
from fastapi.responses import JSONResponse, HTMLResponse
import sys
import os
import hmac
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import logging
import httpx

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mocks.common.base import create_mock_app
from mocks.common.errors import NotFoundError, ValidationError

# Configure logging
logger = logging.getLogger("WebhookReceiver")

# Configuration
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "webhook-secret-123")

# Initialize FastAPI app
app = create_mock_app(
    title="Webhook Receiver Mock",
    description="Mock webhook receiver for testing event notifications",
    version="1.0.0"
)

# In-memory event storage
events: Dict[str, Dict[str, Any]] = {}
client_stats: Dict[str, Dict[str, Any]] = {}


def verify_signature(payload: bytes, signature: Optional[str], secret: str = WEBHOOK_SECRET) -> bool:
    """Verify HMAC-SHA256 signature.

    Args:
        payload: Request body bytes
        signature: Provided signature (hex format)
        secret: Secret key for HMAC

    Returns:
        True if signature valid, False otherwise
    """
    if not signature:
        return False

    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected_signature)


def generate_signature(payload: bytes, secret: str = WEBHOOK_SECRET) -> str:
    """Generate HMAC-SHA256 signature for payload.

    Args:
        payload: Data to sign
        secret: Secret key

    Returns:
        Hex-encoded signature
    """
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


@app.post("/webhooks/{client_id}")
async def receive_webhook(client_id: str, request: Request):
    """Receive and log webhook event.

    Validates HMAC signature if X-Webhook-Signature header present.

    Args:
        client_id: Client identifier
        request: FastAPI request object

    Returns:
        Acknowledgment response

    Raises:
        401: Invalid signature
        400: Invalid JSON payload
    """
    # Read raw body for signature verification
    body_bytes = await request.body()
    signature = request.headers.get("X-Webhook-Signature")

    # Verify signature if provided
    if signature and not verify_signature(body_bytes, signature):
        logger.warning(f"Invalid signature for client {client_id}")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse JSON payload
    try:
        payload = json.loads(body_bytes.decode())
    except json.JSONDecodeError:
        raise ValidationError("Invalid JSON payload")

    # Generate event ID
    event_id = f"evt_{datetime.utcnow().timestamp()}_{client_id}"

    # Store event
    event_data = {
        "event_id": event_id,
        "client_id": client_id,
        "timestamp": datetime.utcnow().isoformat(),
        "payload": payload,
        "headers": dict(request.headers),
        "signature_verified": signature is not None and verify_signature(body_bytes, signature)
    }

    events[event_id] = event_data

    # Update client statistics
    if client_id not in client_stats:
        client_stats[client_id] = {
            "total_events": 0,
            "first_event": datetime.utcnow().isoformat(),
            "last_event": None,
            "event_types": {}
        }

    client_stats[client_id]["total_events"] += 1
    client_stats[client_id]["last_event"] = datetime.utcnow().isoformat()

    event_type = payload.get("event_type", "unknown")
    if event_type not in client_stats[client_id]["event_types"]:
        client_stats[client_id]["event_types"][event_type] = 0
    client_stats[client_id]["event_types"][event_type] += 1

    logger.info(f"Received webhook: {event_id} from {client_id} (type: {event_type})")

    return {
        "status": "received",
        "event_id": event_id,
        "timestamp": event_data["timestamp"],
        "signature_verified": event_data["signature_verified"]
    }


@app.get("/webhooks/events")
async def list_events(
    client_id: Optional[str] = Query(None, description="Filter by client ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(50, ge=1, le=500, description="Max events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """List received webhook events.

    Supports filtering by client_id and event_type.

    Args:
        client_id: Filter by client ID
        event_type: Filter by event type
        limit: Maximum events to return
        offset: Pagination offset

    Returns:
        List of events
    """
    filtered_events = list(events.values())

    # Apply filters
    if client_id:
        filtered_events = [e for e in filtered_events if e["client_id"] == client_id]

    if event_type:
        filtered_events = [
            e for e in filtered_events
            if e.get("payload", {}).get("event_type") == event_type
        ]

    # Sort by timestamp (newest first)
    filtered_events.sort(key=lambda x: x["timestamp"], reverse=True)

    # Pagination
    total = len(filtered_events)
    paginated_events = filtered_events[offset:offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": paginated_events
    }


@app.get("/webhooks/events/{event_id}")
async def get_event(event_id: str = Path(..., description="Event ID")):
    """Get specific webhook event details.

    Args:
        event_id: Event identifier

    Returns:
        Full event details

    Raises:
        404: Event not found
    """
    if event_id not in events:
        raise NotFoundError("Event", event_id)

    return events[event_id]


@app.delete("/webhooks/events")
async def clear_events(
    client_id: Optional[str] = Query(None, description="Clear events for specific client only")
):
    """Clear webhook event history.

    Args:
        client_id: Optional client ID to clear events for specific client

    Returns:
        Deletion confirmation
    """
    if client_id:
        # Clear events for specific client
        events_to_delete = [k for k, v in events.items() if v["client_id"] == client_id]
        for event_id in events_to_delete:
            del events[event_id]

        if client_id in client_stats:
            del client_stats[client_id]

        logger.info(f"Cleared {len(events_to_delete)} events for client {client_id}")

        return {
            "message": f"Events cleared for client {client_id}",
            "events_deleted": len(events_to_delete)
        }
    else:
        # Clear all events
        event_count = len(events)
        events.clear()
        client_stats.clear()

        logger.warning(f"Cleared all events ({event_count} total)")

        return {
            "message": "All events cleared",
            "events_deleted": event_count
        }


@app.post("/webhooks/replay/{event_id}")
async def replay_event(
    event_id: str = Path(..., description="Event ID to replay"),
    target_url: str = Query(..., description="Target URL to send event to"),
    include_signature: bool = Query(True, description="Include HMAC signature")
):
    """Replay a webhook event to another URL.

    Useful for testing webhook integrations.

    Args:
        event_id: Event to replay
        target_url: Destination URL
        include_signature: Whether to include signature

    Returns:
        Replay result

    Raises:
        404: Event not found
    """
    if event_id not in events:
        raise NotFoundError("Event", event_id)

    event = events[event_id]
    payload = event["payload"]
    payload_bytes = json.dumps(payload).encode()

    # Prepare headers
    headers = {"Content-Type": "application/json"}
    if include_signature:
        signature = generate_signature(payload_bytes)
        headers["X-Webhook-Signature"] = signature

    # Send request
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(target_url, json=payload, headers=headers)

        logger.info(f"Replayed event {event_id} to {target_url}: {response.status_code}")

        return {
            "status": "replayed",
            "event_id": event_id,
            "target_url": target_url,
            "response_status": response.status_code,
            "response_body": response.text[:500]  # Truncate for safety
        }

    except Exception as e:
        logger.error(f"Replay failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Replay failed: {str(e)}")


@app.get("/webhooks/stats")
async def get_statistics():
    """Get webhook statistics.

    Returns:
        Overall webhook statistics
    """
    total_events = len(events)
    unique_clients = len(client_stats)

    # Event type distribution
    event_types = {}
    for event in events.values():
        event_type = event.get("payload", {}).get("event_type", "unknown")
        event_types[event_type] = event_types.get(event_type, 0) + 1

    return {
        "total_events": total_events,
        "unique_clients": unique_clients,
        "event_type_distribution": event_types,
        "client_stats": client_stats,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/", response_class=HTMLResponse)
async def webhook_dashboard():
    """Serve webhook dashboard UI."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Webhook Receiver Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 { color: #569cd6; margin-bottom: 20px; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #252526;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #569cd6;
        }
        .stat-value {
            font-size: 36px;
            font-weight: bold;
            color: #4ec9b0;
        }
        .stat-label {
            color: #858585;
            margin-top: 5px;
        }
        .events {
            background: #252526;
            border-radius: 8px;
            padding: 20px;
        }
        .event {
            background: #1e1e1e;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 15px;
            border-left: 4px solid #4ec9b0;
        }
        .event-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        .event-id {
            color: #569cd6;
            font-weight: bold;
        }
        .event-time {
            color: #858585;
        }
        .event-payload {
            background: #1e1e1e;
            padding: 10px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            overflow-x: auto;
        }
        .btn {
            background: #569cd6;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            margin-right: 10px;
        }
        .btn:hover {
            background: #4b88c0;
        }
        .btn-danger {
            background: #f48771;
        }
        .btn-danger:hover {
            background: #d66f5e;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📡 Webhook Receiver Dashboard</h1>

        <div class="stats" id="stats"></div>

        <div class="events">
            <h2>Recent Events</h2>
            <button class="btn" onclick="loadEvents()">Refresh</button>
            <button class="btn btn-danger" onclick="clearEvents()">Clear All</button>
            <div id="events" style="margin-top: 20px;"></div>
        </div>
    </div>

    <script>
        async function loadStats() {
            const response = await fetch('/webhooks/stats');
            const stats = await response.json();

            document.getElementById('stats').innerHTML = `
                <div class="stat-card">
                    <div class="stat-value">${stats.total_events}</div>
                    <div class="stat-label">Total Events</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${stats.unique_clients}</div>
                    <div class="stat-label">Unique Clients</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${Object.keys(stats.event_type_distribution).length}</div>
                    <div class="stat-label">Event Types</div>
                </div>
            `;
        }

        async function loadEvents() {
            const response = await fetch('/webhooks/events?limit=20');
            const data = await response.json();

            const eventsHTML = data.events.map(event => `
                <div class="event">
                    <div class="event-header">
                        <span class="event-id">${event.event_id}</span>
                        <span class="event-time">${new Date(event.timestamp).toLocaleString()}</span>
                    </div>
                    <p><strong>Client:</strong> ${event.client_id}</p>
                    <p><strong>Signature Verified:</strong> ${event.signature_verified ? '✅' : '❌'}</p>
                    <div class="event-payload">${JSON.stringify(event.payload, null, 2)}</div>
                </div>
            `).join('');

            document.getElementById('events').innerHTML = eventsHTML || '<p>No events received yet</p>';
        }

        async function clearEvents() {
            if (!confirm('Clear all events?')) return;

            await fetch('/webhooks/events', { method: 'DELETE' });
            loadStats();
            loadEvents();
        }

        // Auto-refresh every 5 seconds
        setInterval(() => {
            loadStats();
            loadEvents();
        }, 5000);

        // Initial load
        loadStats();
        loadEvents();
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "4000"))
    logger.info(f"Starting Webhook Receiver Mock on port {port}")
    logger.info(f"Webhook secret: {WEBHOOK_SECRET}")
    logger.info("Access dashboard at: http://localhost:4000")

    uvicorn.run(app, host="0.0.0.0", port=port)
