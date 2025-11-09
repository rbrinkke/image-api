"""
S3 Mock Integration Test
========================

Demonstrates integration between image API and S3 mock server.
Tests storage operations without AWS dependencies.

Prerequisites:
    - S3 mock running on localhost:9000
    - Python packages: aioboto3, asyncio

Usage:
    python examples/s3_integration_test.py
"""

import asyncio
import aioboto3
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_s3_mock_integration():
    """Test S3 mock with aioboto3 (same library used by image API)."""

    print("🧪 S3 Mock Integration Test")
    print("=" * 60)

    # Configure S3 client to use mock
    session = aioboto3.Session()

    async with session.client(
        's3',
        endpoint_url='http://localhost:9000',
        aws_access_key_id='test-key',
        aws_secret_access_key='test-secret',
        region_name='eu-west-1'
    ) as s3:

        # Test 1: Upload object
        print("\n1️⃣  Testing PutObject...")
        test_content = b"Hello, S3 Mock! This is test image data."

        try:
            response = await s3.put_object(
                Bucket='test-bucket',
                Key='images/test-image.jpg',
                Body=test_content,
                ServerSideEncryption='AES256'
            )
            print(f"   ✅ Upload successful!")
            print(f"   ETag: {response['ETag']}")
            print(f"   Encryption: {response.get('ServerSideEncryption', 'N/A')}")
        except Exception as e:
            print(f"   ❌ Upload failed: {e}")
            return

        # Test 2: Download object
        print("\n2️⃣  Testing GetObject...")
        try:
            response = await s3.get_object(
                Bucket='test-bucket',
                Key='images/test-image.jpg'
            )
            downloaded_content = await response['Body'].read()

            if downloaded_content == test_content:
                print(f"   ✅ Download successful!")
                print(f"   Size: {len(downloaded_content)} bytes")
                print(f"   Content matches: True")
            else:
                print(f"   ❌ Content mismatch!")
        except Exception as e:
            print(f"   ❌ Download failed: {e}")
            return

        # Test 3: Generate presigned URL (note: this doesn't work with aioboto3 directly with mock)
        print("\n3️⃣  Testing Presigned URL...")
        try:
            # Use mock's HTTP endpoint instead
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:9000/presigned-url",
                    params={
                        "bucket": "test-bucket",
                        "key": "images/test-image.jpg",
                        "expires_in": 3600
                    }
                )
                if response.status_code == 200:
                    presigned_data = response.json()
                    print(f"   ✅ Presigned URL generated!")
                    print(f"   URL: {presigned_data['url'][:80]}...")
                    print(f"   Expires: {presigned_data['expires_at']}")
                else:
                    print(f"   ❌ Presigned URL generation failed: {response.status_code}")
        except Exception as e:
            print(f"   ⚠️  Presigned URL test skipped: {e}")

        # Test 4: List objects (using admin endpoint)
        print("\n4️⃣  Testing ListObjects (Admin)...")
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:9000/admin/buckets")
                if response.status_code == 200:
                    buckets = response.json()
                    print(f"   ✅ List successful!")
                    for bucket_name, info in buckets.items():
                        print(f"   Bucket: {bucket_name}")
                        print(f"     Objects: {info['object_count']}")
                        print(f"     Size: {info['total_size_mb']} MB")
                else:
                    print(f"   ❌ List failed: {response.status_code}")
        except Exception as e:
            print(f"   ❌ List failed: {e}")

        # Test 5: Delete object
        print("\n5️⃣  Testing DeleteObject...")
        try:
            await s3.delete_object(
                Bucket='test-bucket',
                Key='images/test-image.jpg'
            )
            print(f"   ✅ Delete successful!")

            # Verify deletion
            try:
                await s3.get_object(Bucket='test-bucket', Key='images/test-image.jpg')
                print(f"   ❌ Object still exists after deletion!")
            except Exception:
                print(f"   ✅ Verified: Object no longer exists")

        except Exception as e:
            print(f"   ❌ Delete failed: {e}")

        # Test 6: Multiple uploads (simulate batch processing)
        print("\n6️⃣  Testing Batch Upload...")
        try:
            for i in range(5):
                await s3.put_object(
                    Bucket='test-bucket',
                    Key=f'batch/image-{i}.jpg',
                    Body=f"Batch image {i}".encode(),
                    ServerSideEncryption='AES256'
                )

            print(f"   ✅ Uploaded 5 objects successfully!")

            # Check bucket stats
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:9000/admin/buckets")
                buckets = response.json()
                print(f"   Total objects in test-bucket: {buckets['test-bucket']['object_count']}")

        except Exception as e:
            print(f"   ❌ Batch upload failed: {e}")

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("\n💡 Tips:")
    print("   - View all buckets: curl http://localhost:9000/admin/buckets")
    print("   - View bucket objects: curl http://localhost:9000/admin/objects/test-bucket")
    print("   - Clear all data: curl -X DELETE http://localhost:9000/admin/reset")
    print("   - OpenAPI docs: http://localhost:9000/docs")


if __name__ == "__main__":
    # Check if S3 mock is running
    import httpx

    try:
        response = httpx.get("http://localhost:9000/health", timeout=2.0)
        if response.status_code != 200:
            print("❌ S3 mock is not responding. Start it with: python s3_mock.py")
            sys.exit(1)
    except Exception:
        print("❌ S3 mock is not running. Start it with: python s3_mock.py")
        sys.exit(1)

    # Run tests
    asyncio.run(test_s3_mock_integration())
