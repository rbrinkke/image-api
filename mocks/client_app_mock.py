"""
Client Application Mock
========================

Mock client application demonstrating image API integration.
Features drag-drop upload, JWT generation, job polling, and result display.

Usage:
    python client_app_mock.py
    # or
    uvicorn client_app_mock:app --reload --port 3000

Endpoints:
    GET /                             - Upload UI (HTML)
    POST /api/upload                  - Trigger image upload to API
    GET /api/status/{job_id}          - Poll job status
    GET /api/result/{job_id}          - Fetch final result
    POST /api/stress-test             - Rate limit test (50+ uploads)
    GET /api/generate-token           - Generate test JWT
    GET /health                       - Health check

Configuration:
    IMAGE_API_URL: Image API base URL (default: http://localhost:8002)
    JWT_SECRET: JWT secret key (default: dev-secret-change-in-production)
    PORT: Server port (default: 3000)
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import sys
import os
import httpx
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mocks.common.base import create_mock_app
from mocks.common.auth import generate_test_jwt

# Configure logging
logger = logging.getLogger("ClientAppMock")

# Configuration
IMAGE_API_URL = os.getenv("IMAGE_API_URL", "http://localhost:8002")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")

# Initialize FastAPI app
app = create_mock_app(
    title="Client Application Mock",
    description="Mock client demonstrating image API integration",
    version="1.0.0"
)

# In-memory storage for tracking uploads
upload_history: Dict[str, Dict[str, Any]] = {}


@app.get("/", response_class=HTMLResponse)
async def upload_ui():
    """Serve interactive upload UI."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image Upload Client - Mock</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 32px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 16px;
        }
        .upload-zone {
            border: 3px dashed #667eea;
            border-radius: 8px;
            padding: 60px 40px;
            text-align: center;
            background: #f8f9ff;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        .upload-zone:hover {
            background: #eef1ff;
            border-color: #764ba2;
        }
        .upload-zone.dragover {
            background: #e3e8ff;
            border-color: #764ba2;
            transform: scale(1.02);
        }
        .upload-icon {
            font-size: 48px;
            margin-bottom: 20px;
        }
        input[type="file"] {
            display: none;
        }
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 14px 32px;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s ease;
            margin-top: 20px;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }
        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }
        .status {
            margin-top: 30px;
            padding: 20px;
            border-radius: 8px;
            background: #f8f9fa;
        }
        .status.pending { background: #fff3cd; border-left: 4px solid #ffc107; }
        .status.processing { background: #d1ecf1; border-left: 4px solid #17a2b8; }
        .status.completed { background: #d4edda; border-left: 4px solid #28a745; }
        .status.failed { background: #f8d7da; border-left: 4px solid #dc3545; }
        .result-images {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .result-image {
            text-align: center;
        }
        .result-image img {
            max-width: 100%;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        .result-image p {
            margin-top: 10px;
            font-weight: 600;
            color: #667eea;
        }
        .config {
            margin-top: 20px;
            padding: 15px;
            background: #f0f0f0;
            border-radius: 6px;
            font-size: 14px;
        }
        .config label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            color: #333;
        }
        .config input, .config select {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            margin-bottom: 10px;
        }
        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .logs {
            margin-top: 20px;
            padding: 15px;
            background: #1e1e1e;
            color: #d4d4d4;
            border-radius: 6px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
        }
        .log-entry {
            margin-bottom: 5px;
        }
        .log-time {
            color: #858585;
        }
        .log-info {
            color: #4ec9b0;
        }
        .log-error {
            color: #f48771;
        }
        .log-success {
            color: #b5cea8;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🖼️ Image Upload Client</h1>
        <p class="subtitle">Mock client for testing the Image Processing API</p>

        <div class="config">
            <label>User ID (JWT Subject):</label>
            <input type="text" id="userId" value="test-user-123">

            <label>Bucket:</label>
            <input type="text" id="bucket" value="test-uploads">

            <label>Context:</label>
            <input type="text" id="context" value="demo-upload">
        </div>

        <div class="upload-zone" id="uploadZone">
            <div class="upload-icon">📤</div>
            <h3>Drag & Drop Image Here</h3>
            <p style="color: #666; margin-top: 10px;">or click to browse</p>
            <input type="file" id="fileInput" accept="image/jpeg,image/png,image/webp">
        </div>

        <button class="btn" id="uploadBtn" disabled>Upload Image</button>
        <button class="btn" id="stressTestBtn">Stress Test (50 uploads)</button>

        <div id="statusContainer"></div>

        <div class="logs" id="logs"></div>
    </div>

    <script>
        const uploadZone = document.getElementById('uploadZone');
        const fileInput = document.getElementById('fileInput');
        const uploadBtn = document.getElementById('uploadBtn');
        const stressTestBtn = document.getElementById('stressTestBtn');
        const statusContainer = document.getElementById('statusContainer');
        const logs = document.getElementById('logs');

        let selectedFile = null;
        let pollingInterval = null;

        // Drag and drop handlers
        uploadZone.addEventListener('click', () => fileInput.click());
        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });
        uploadZone.addEventListener('dragleave', () => {
            uploadZone.classList.remove('dragover');
        });
        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                selectedFile = e.dataTransfer.files[0];
                updateUI();
            }
        });
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                selectedFile = e.target.files[0];
                updateUI();
            }
        });

        function updateUI() {
            if (selectedFile) {
                uploadZone.querySelector('h3').textContent = `Selected: ${selectedFile.name}`;
                uploadBtn.disabled = false;
            }
        }

        function addLog(message, type = 'info') {
            const time = new Date().toLocaleTimeString();
            const logEntry = document.createElement('div');
            logEntry.className = `log-entry log-${type}`;
            logEntry.innerHTML = `<span class="log-time">[${time}]</span> ${message}`;
            logs.appendChild(logEntry);
            logs.scrollTop = logs.scrollHeight;
        }

        // Upload handler
        uploadBtn.addEventListener('click', async () => {
            if (!selectedFile) return;

            uploadBtn.disabled = true;
            uploadBtn.innerHTML = '<span class="spinner"></span> Uploading...';
            addLog('Starting upload...', 'info');

            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('bucket', document.getElementById('bucket').value);
            formData.append('user_id', document.getElementById('userId').value);
            formData.append('context', document.getElementById('context').value);

            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (response.ok) {
                    addLog(`✅ Upload accepted! Job ID: ${result.job_id}`, 'success');
                    startPolling(result.job_id);
                } else {
                    addLog(`❌ Upload failed: ${result.detail || result.message}`, 'error');
                    uploadBtn.disabled = false;
                    uploadBtn.textContent = 'Upload Image';
                }
            } catch (error) {
                addLog(`❌ Error: ${error.message}`, 'error');
                uploadBtn.disabled = false;
                uploadBtn.textContent = 'Upload Image';
            }
        });

        // Polling
        async function startPolling(jobId) {
            addLog(`🔄 Polling job status...`, 'info');

            pollingInterval = setInterval(async () => {
                try {
                    const response = await fetch(`/api/status/${jobId}`);
                    const status = await response.json();

                    updateStatus(status);

                    if (status.status === 'completed') {
                        clearInterval(pollingInterval);
                        addLog(`✅ Processing completed!`, 'success');
                        await fetchResult(jobId);
                        uploadBtn.disabled = false;
                        uploadBtn.textContent = 'Upload Image';
                    } else if (status.status === 'failed') {
                        clearInterval(pollingInterval);
                        addLog(`❌ Processing failed: ${status.error}`, 'error');
                        uploadBtn.disabled = false;
                        uploadBtn.textContent = 'Upload Image';
                    }
                } catch (error) {
                    addLog(`⚠️ Polling error: ${error.message}`, 'error');
                }
            }, 2000);
        }

        function updateStatus(status) {
            statusContainer.innerHTML = `
                <div class="status ${status.status}">
                    <h3>Status: ${status.status.toUpperCase()}</h3>
                    <p><strong>Job ID:</strong> ${status.job_id}</p>
                    <p><strong>Image ID:</strong> ${status.image_id}</p>
                    <p><strong>Attempts:</strong> ${status.attempts || 0}</p>
                    ${status.error ? `<p style="color: red;"><strong>Error:</strong> ${status.error}</p>` : ''}
                </div>
            `;
        }

        async function fetchResult(jobId) {
            try {
                const response = await fetch(`/api/result/${jobId}`);
                const result = await response.json();

                if (result.urls) {
                    displayResults(result);
                }
            } catch (error) {
                addLog(`⚠️ Failed to fetch result: ${error.message}`, 'error');
            }
        }

        function displayResults(result) {
            const urls = result.urls;
            const imagesHTML = Object.entries(urls).map(([size, url]) => `
                <div class="result-image">
                    <img src="${url}" alt="${size}" loading="lazy">
                    <p>${size.toUpperCase()}</p>
                </div>
            `).join('');

            statusContainer.innerHTML += `
                <div class="result-images">
                    ${imagesHTML}
                </div>
                <p style="margin-top: 15px;"><strong>Dominant Color:</strong>
                    <span style="display: inline-block; width: 30px; height: 30px; background: ${result.dominant_color}; border-radius: 4px; vertical-align: middle;"></span>
                    ${result.dominant_color}
                </p>
            `;
        }

        // Stress test
        stressTestBtn.addEventListener('click', async () => {
            if (!confirm('Send 51 rapid uploads to test rate limiting?')) return;

            stressTestBtn.disabled = true;
            addLog('🔥 Starting stress test...', 'info');

            try {
                const response = await fetch('/api/stress-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: document.getElementById('userId').value,
                        count: 51
                    })
                });

                const result = await response.json();
                addLog(`📊 Stress test complete: ${result.successful} successful, ${result.rate_limited} rate limited`, 'success');
            } catch (error) {
                addLog(`❌ Stress test error: ${error.message}`, 'error');
            } finally {
                stressTestBtn.disabled = false;
            }
        });

        // Initial log
        addLog('Client application ready', 'success');
        addLog(`API URL: ${window.location.origin}`, 'info');
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


@app.post("/api/upload")
async def upload_to_api(
    file: UploadFile = File(...),
    bucket: str = Form(...),
    user_id: str = Form("test-user-123"),
    context: str = Form("demo")
):
    """Upload image to the real image API.

    Generates JWT token, sends upload request, returns job_id.

    Args:
        file: Image file
        bucket: Storage bucket name
        user_id: User identifier (for JWT)
        context: Upload context

    Returns:
        Job information from API
    """
    # Generate JWT token
    token = generate_test_jwt(user_id=user_id, secret=JWT_SECRET)

    # Prepare upload request
    metadata = {"context": context, "client": "mock-app"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Read file content
            file_content = await file.read()
            await file.seek(0)  # Reset file pointer

            # Upload to API
            files = {"file": (file.filename, file_content, file.content_type)}
            data = {
                "bucket": bucket,
                "metadata": str(metadata)
            }
            headers = {"Authorization": f"Bearer {token}"}

            response = await client.post(
                f"{IMAGE_API_URL}/api/v1/images/upload",
                files=files,
                data=data,
                headers=headers
            )

            if response.status_code == 202:
                result = response.json()
                upload_history[result["job_id"]] = {
                    "uploaded_at": datetime.utcnow().isoformat(),
                    "user_id": user_id,
                    "filename": file.filename,
                    "status": "pending"
                }
                logger.info(f"Upload successful: {result['job_id']}")
                return result
            else:
                logger.error(f"Upload failed: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.json() if response.headers.get("content-type") == "application/json" else response.text
                )

    except httpx.RequestError as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Cannot connect to image API: {str(e)}")


@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    """Poll job status from the image API.

    Args:
        job_id: Job identifier

    Returns:
        Job status from API
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{IMAGE_API_URL}/api/v1/images/jobs/{job_id}")

            if response.status_code == 200:
                status = response.json()
                if job_id in upload_history:
                    upload_history[job_id]["status"] = status["status"]
                return status
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)

    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Cannot connect to image API: {str(e)}")


@app.get("/api/result/{job_id}")
async def get_job_result(job_id: str):
    """Fetch final processing result from the image API.

    Args:
        job_id: Job identifier

    Returns:
        Processing result with URLs
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{IMAGE_API_URL}/api/v1/images/jobs/{job_id}/result")

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=response.status_code, detail=response.text)

    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Cannot connect to image API: {str(e)}")


@app.post("/api/stress-test")
async def stress_test(user_id: str = Form("test-user-123"), count: int = Form(51)):
    """Stress test: send multiple rapid uploads to test rate limiting.

    Args:
        user_id: User identifier
        count: Number of uploads to attempt

    Returns:
        Stress test results
    """
    token = generate_test_jwt(user_id=user_id, secret=JWT_SECRET)
    successful = 0
    rate_limited = 0
    errors = 0

    # Create a dummy image file content
    dummy_content = b"fake-image-content-for-stress-testing"

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(count):
            try:
                files = {"file": (f"stress-test-{i}.jpg", dummy_content, "image/jpeg")}
                data = {"bucket": "stress-test", "metadata": '{"context":"stress-test"}'}
                headers = {"Authorization": f"Bearer {token}"}

                response = await client.post(
                    f"{IMAGE_API_URL}/api/v1/images/upload",
                    files=files,
                    data=data,
                    headers=headers
                )

                if response.status_code == 202:
                    successful += 1
                elif response.status_code == 429:
                    rate_limited += 1
                    logger.info(f"Rate limited at upload {i+1}")
                else:
                    errors += 1

            except Exception as e:
                errors += 1
                logger.error(f"Stress test error: {str(e)}")

    return {
        "total_attempts": count,
        "successful": successful,
        "rate_limited": rate_limited,
        "errors": errors,
        "user_id": user_id
    }


@app.get("/api/generate-token")
async def generate_token(user_id: str = "test-user-123", expires_minutes: int = 60):
    """Generate a test JWT token.

    Args:
        user_id: User identifier
        expires_minutes: Token expiration

    Returns:
        JWT token
    """
    token = generate_test_jwt(user_id=user_id, secret=JWT_SECRET, expires_minutes=expires_minutes)
    return {
        "token": token,
        "user_id": user_id,
        "expires_minutes": expires_minutes,
        "usage": f"Authorization: Bearer {token}"
    }


@app.get("/api/history")
async def get_upload_history():
    """Get upload history from this session.

    Returns:
        Upload history
    """
    return {
        "total_uploads": len(upload_history),
        "uploads": upload_history
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "3000"))
    logger.info(f"Starting Client Application Mock on port {port}")
    logger.info(f"Image API URL: {IMAGE_API_URL}")
    logger.info("Access UI at: http://localhost:3000")

    uvicorn.run(app, host="0.0.0.0", port=port)
