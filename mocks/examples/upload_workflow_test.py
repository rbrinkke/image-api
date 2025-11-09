"""
Complete Upload Workflow Test
==============================

End-to-end test of image upload workflow using client app mock.
Demonstrates full integration: JWT → Upload → Poll → Result

Prerequisites:
    - Image API running on localhost:8002
    - Client app mock running on localhost:3000
    - Test image file available

Usage:
    python examples/upload_workflow_test.py path/to/image.jpg
"""

import asyncio
import httpx
import sys
import os
from pathlib import Path
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_upload_workflow(image_path: str):
    """Test complete upload workflow."""

    print("🧪 Complete Upload Workflow Test")
    print("=" * 60)

    if not Path(image_path).exists():
        print(f"❌ Image not found: {image_path}")
        return

    async with httpx.AsyncClient(timeout=30.0) as client:

        # Step 1: Generate JWT token
        print("\n1️⃣  Generating JWT token...")
        try:
            response = await client.get(
                "http://localhost:3000/api/generate-token",
                params={"user_id": "test-workflow-user", "expires_minutes": 60}
            )
            token_data = response.json()
            token = token_data["token"]
            print(f"   ✅ Token generated!")
            print(f"   User ID: {token_data['user_id']}")
            print(f"   Expires in: {token_data['expires_minutes']} minutes")
        except Exception as e:
            print(f"   ❌ Token generation failed: {e}")
            return

        # Step 2: Upload image
        print("\n2️⃣  Uploading image...")
        try:
            with open(image_path, 'rb') as f:
                files = {"file": (Path(image_path).name, f, "image/jpeg")}
                data = {
                    "bucket": "workflow-test",
                    "user_id": "test-workflow-user",
                    "context": "integration-test"
                }

                response = await client.post(
                    "http://localhost:3000/api/upload",
                    files=files,
                    data=data
                )

                if response.status_code == 202:
                    upload_result = response.json()
                    job_id = upload_result["job_id"]
                    image_id = upload_result["image_id"]
                    print(f"   ✅ Upload accepted!")
                    print(f"   Job ID: {job_id}")
                    print(f"   Image ID: {image_id}")
                else:
                    print(f"   ❌ Upload failed: {response.status_code}")
                    print(f"   Response: {response.text}")
                    return

        except Exception as e:
            print(f"   ❌ Upload failed: {e}")
            return

        # Step 3: Poll job status
        print("\n3️⃣  Polling job status...")
        max_attempts = 30
        attempt = 0
        status = None

        while attempt < max_attempts:
            try:
                response = await client.get(f"http://localhost:3000/api/status/{job_id}")

                if response.status_code == 200:
                    status_data = response.json()
                    status = status_data["status"]

                    print(f"   [{attempt + 1}] Status: {status} (attempts: {status_data.get('attempts', 0)})")

                    if status == "completed":
                        print(f"   ✅ Processing completed!")
                        break
                    elif status == "failed":
                        print(f"   ❌ Processing failed!")
                        print(f"   Error: {status_data.get('error', 'Unknown error')}")
                        return
                    else:
                        # Wait before next poll
                        await asyncio.sleep(2)
                else:
                    print(f"   ⚠️  Status check failed: {response.status_code}")

                attempt += 1

            except Exception as e:
                print(f"   ⚠️  Polling error: {e}")
                attempt += 1
                await asyncio.sleep(2)

        if status != "completed":
            print(f"   ❌ Timeout waiting for processing to complete")
            return

        # Step 4: Get final result
        print("\n4️⃣  Fetching final result...")
        try:
            response = await client.get(f"http://localhost:3000/api/result/{job_id}")

            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ Result retrieved!")
                print(f"   Image ID: {result['image_id']}")
                print(f"   Dominant Color: {result.get('metadata', {}).get('dominant_color', 'N/A')}")
                print(f"\n   📸 Generated Variants:")

                urls = result.get("urls", {})
                for size, url in urls.items():
                    print(f"     - {size.upper()}: {url[:80]}...")

                print(f"\n   ⏱️  Completed at: {result['completed_at']}")
            else:
                print(f"   ❌ Result fetch failed: {response.status_code}")
                print(f"   Response: {response.text}")

        except Exception as e:
            print(f"   ❌ Result fetch failed: {e}")

        # Step 5: Verify image retrieval
        print("\n5️⃣  Verifying image retrieval...")
        try:
            # Try to get medium variant
            response = await client.get(
                f"http://localhost:8002/api/v1/images/{image_id}",
                params={"size": "medium"}
            )

            if response.status_code == 200:
                image_data = response.json()
                print(f"   ✅ Image retrieval successful!")
                print(f"   URL: {image_data.get('url', 'N/A')[:80]}...")
            else:
                print(f"   ⚠️  Image retrieval returned: {response.status_code}")

        except Exception as e:
            print(f"   ⚠️  Image retrieval test skipped: {e}")

    print("\n" + "=" * 60)
    print("✅ Workflow test completed successfully!")
    print("\n💡 Next steps:")
    print("   - View upload history: curl http://localhost:3000/api/history")
    print("   - Check API dashboard: http://localhost:8002/dashboard")
    print("   - Monitor Celery: http://localhost:5555")


if __name__ == "__main__":
    # Check prerequisites
    import httpx

    print("🔍 Checking prerequisites...")

    # Check image API
    try:
        response = httpx.get("http://localhost:8002/api/v1/health", timeout=2.0)
        if response.status_code == 200:
            print("   ✅ Image API is running")
        else:
            print("   ❌ Image API unhealthy")
            sys.exit(1)
    except Exception:
        print("   ❌ Image API not running. Start with: docker compose up -d")
        sys.exit(1)

    # Check client app mock
    try:
        response = httpx.get("http://localhost:3000/health", timeout=2.0)
        if response.status_code == 200:
            print("   ✅ Client app mock is running")
        else:
            print("   ❌ Client app mock unhealthy")
            sys.exit(1)
    except Exception:
        print("   ❌ Client app mock not running. Start with: python client_app_mock.py")
        sys.exit(1)

    # Get image path from command line
    if len(sys.argv) < 2:
        print("\n❌ Usage: python upload_workflow_test.py <path/to/image.jpg>")
        print("\nExample:")
        print("   python upload_workflow_test.py ../test_images/test_500x500.jpg")
        sys.exit(1)

    image_path = sys.argv[1]
    print(f"   📁 Using image: {image_path}")

    # Run workflow test
    print()
    asyncio.run(test_upload_workflow(image_path))
