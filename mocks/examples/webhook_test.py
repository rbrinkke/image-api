"""
Webhook Integration Test
=========================

Test webhook receiver mock with signature verification.
Demonstrates event sending, filtering, and replay.

Prerequisites:
    - Webhook receiver mock running on localhost:4000

Usage:
    python examples/webhook_test.py
"""

import asyncio
import httpx
import json
import hmac
import hashlib
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


WEBHOOK_SECRET = "webhook-secret-123"


def generate_signature(payload: dict) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    payload_bytes = json.dumps(payload).encode()
    return hmac.new(
        WEBHOOK_SECRET.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()


async def test_webhook_integration():
    """Test webhook receiver functionality."""

    print("🧪 Webhook Integration Test")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=10.0) as client:

        # Test 1: Send webhook without signature
        print("\n1️⃣  Testing webhook without signature...")
        payload = {
            "event_type": "image.uploaded",
            "image_id": "test-image-123",
            "job_id": "test-job-456",
            "timestamp": datetime.utcnow().isoformat()
        }

        try:
            response = await client.post(
                "http://localhost:4000/webhooks/client-alpha",
                json=payload
            )

            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ Webhook received!")
                print(f"   Event ID: {result['event_id']}")
                print(f"   Signature verified: {result['signature_verified']}")
            else:
                print(f"   ❌ Webhook failed: {response.status_code}")

        except Exception as e:
            print(f"   ❌ Webhook failed: {e}")
            return

        # Test 2: Send webhook with valid signature
        print("\n2️⃣  Testing webhook with valid signature...")
        payload = {
            "event_type": "image.processed",
            "image_id": "test-image-789",
            "job_id": "test-job-101",
            "status": "completed",
            "urls": {
                "thumbnail": "http://example.com/thumb.jpg",
                "medium": "http://example.com/medium.jpg"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        signature = generate_signature(payload)

        try:
            response = await client.post(
                "http://localhost:4000/webhooks/client-alpha",
                json=payload,
                headers={"X-Webhook-Signature": signature}
            )

            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ Webhook received!")
                print(f"   Event ID: {result['event_id']}")
                print(f"   Signature verified: {result['signature_verified']}")

                if result['signature_verified']:
                    print(f"   ✅ Signature validation passed!")
                else:
                    print(f"   ❌ Signature validation failed!")

            else:
                print(f"   ❌ Webhook failed: {response.status_code}")

        except Exception as e:
            print(f"   ❌ Webhook failed: {e}")

        # Test 3: Send webhook with invalid signature
        print("\n3️⃣  Testing webhook with invalid signature...")
        try:
            response = await client.post(
                "http://localhost:4000/webhooks/client-alpha",
                json=payload,
                headers={"X-Webhook-Signature": "invalid-signature"}
            )

            if response.status_code == 401:
                print(f"   ✅ Invalid signature rejected (401)")
            else:
                print(f"   ⚠️  Expected 401, got {response.status_code}")

        except Exception as e:
            print(f"   ❌ Test failed: {e}")

        # Test 4: Send multiple events from different clients
        print("\n4️⃣  Testing multiple clients...")
        clients = ["client-alpha", "client-beta", "client-gamma"]
        event_types = ["image.uploaded", "image.processing", "image.completed", "image.failed"]

        for i in range(10):
            client_id = clients[i % len(clients)]
            event_type = event_types[i % len(event_types)]

            payload = {
                "event_type": event_type,
                "image_id": f"image-{i}",
                "job_id": f"job-{i}",
                "timestamp": datetime.utcnow().isoformat()
            }

            signature = generate_signature(payload)

            try:
                response = await client.post(
                    f"http://localhost:4000/webhooks/{client_id}",
                    json=payload,
                    headers={"X-Webhook-Signature": signature}
                )

                if response.status_code == 200:
                    print(f"   [{i+1}/10] ✅ {client_id}: {event_type}")
                else:
                    print(f"   [{i+1}/10] ❌ {client_id}: Failed")

            except Exception as e:
                print(f"   [{i+1}/10] ❌ Error: {e}")

            # Small delay to avoid overwhelming
            await asyncio.sleep(0.1)

        # Test 5: List all events
        print("\n5️⃣  Listing all events...")
        try:
            response = await client.get("http://localhost:4000/webhooks/events?limit=50")

            if response.status_code == 200:
                events_data = response.json()
                print(f"   ✅ Retrieved {events_data['total']} events")
                print(f"   Showing {len(events_data['events'])} events")
            else:
                print(f"   ❌ List failed: {response.status_code}")

        except Exception as e:
            print(f"   ❌ List failed: {e}")

        # Test 6: Filter events by client
        print("\n6️⃣  Filtering events by client...")
        try:
            response = await client.get(
                "http://localhost:4000/webhooks/events",
                params={"client_id": "client-alpha", "limit": 20}
            )

            if response.status_code == 200:
                events_data = response.json()
                print(f"   ✅ Found {events_data['total']} events for client-alpha")

                # Verify all events are from correct client
                all_correct = all(
                    event['client_id'] == 'client-alpha'
                    for event in events_data['events']
                )
                if all_correct:
                    print(f"   ✅ Filter working correctly!")
                else:
                    print(f"   ❌ Filter returned wrong clients!")

            else:
                print(f"   ❌ Filter failed: {response.status_code}")

        except Exception as e:
            print(f"   ❌ Filter failed: {e}")

        # Test 7: Get statistics
        print("\n7️⃣  Getting webhook statistics...")
        try:
            response = await client.get("http://localhost:4000/webhooks/stats")

            if response.status_code == 200:
                stats = response.json()
                print(f"   ✅ Statistics retrieved!")
                print(f"   Total events: {stats['total_events']}")
                print(f"   Unique clients: {stats['unique_clients']}")
                print(f"   Event types: {len(stats['event_type_distribution'])}")

                print(f"\n   📊 Event Type Distribution:")
                for event_type, count in stats['event_type_distribution'].items():
                    print(f"     - {event_type}: {count}")

            else:
                print(f"   ❌ Stats failed: {response.status_code}")

        except Exception as e:
            print(f"   ❌ Stats failed: {e}")

        # Test 8: Clear events for specific client
        print("\n8️⃣  Clearing events for client-beta...")
        try:
            response = await client.delete(
                "http://localhost:4000/webhooks/events",
                params={"client_id": "client-beta"}
            )

            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ Cleared {result['events_deleted']} events")
            else:
                print(f"   ❌ Clear failed: {response.status_code}")

        except Exception as e:
            print(f"   ❌ Clear failed: {e}")

    print("\n" + "=" * 60)
    print("✅ All webhook tests completed!")
    print("\n💡 Tips:")
    print("   - View dashboard: http://localhost:4000")
    print("   - List events: curl http://localhost:4000/webhooks/events")
    print("   - Get stats: curl http://localhost:4000/webhooks/stats")
    print("   - Clear all: curl -X DELETE http://localhost:4000/webhooks/events")


if __name__ == "__main__":
    # Check if webhook receiver is running
    import httpx

    try:
        response = httpx.get("http://localhost:4000/health", timeout=2.0)
        if response.status_code != 200:
            print("❌ Webhook receiver is not responding. Start it with: python webhook_receiver_mock.py")
            sys.exit(1)
    except Exception:
        print("❌ Webhook receiver is not running. Start it with: python webhook_receiver_mock.py")
        sys.exit(1)

    # Run tests
    asyncio.run(test_webhook_integration())
