# OAuth 2.0 Integration Guide for Image API

**Date:** 2025-11-12
**Auth API:** https://github.com/rbrinkke/auth-api
**Status:** ✅ Auth API OAuth 2.0 Ready (23/23 tests passing)

---

## 🎯 Overview

This guide explains how Image API can authenticate users and validate tokens from Auth API's OAuth 2.0 Authorization Server.

**Architecture:**
```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Frontend   │─────▶│   Auth API   │      │   Image API  │
│  (User/App)  │      │  OAuth Server│◀─────│  (Resource)  │
└──────────────┘      └──────────────┘      └──────────────┘
   1. Upload           2. Issues Token       3. Validates Token
```

---

## 🔑 Token Validation Strategy

Auth API uses **HS256 (symmetric)** JWT tokens with a **shared secret**. This is the **recommended approach** for internal microservices.

### Why HS256 is Perfect Here

✅ **Faster** - No asymmetric crypto overhead
✅ **Simpler** - No JWKS endpoint needed
✅ **Secure** - When JWT_SECRET_KEY is properly protected
✅ **RFC Compliant** - OAuth 2.0 doesn't mandate RS256

**Auth API and Image API share the same JWT_SECRET_KEY for validation.**

---

## 📋 Prerequisites

### 1. Environment Variables

Add to Image API's `.env` file:

```bash
# OAuth 2.0 Configuration
AUTH_API_URL=http://auth-api:8000
JWT_SECRET_KEY=<SAME_SECRET_AS_AUTH_API>
JWT_ALGORITHM=HS256

# Optional: OAuth Client Registration (if Image API acts as OAuth client)
OAUTH_CLIENT_ID=image-api-service
OAUTH_CLIENT_SECRET=<your-client-secret>
```

⚠️ **CRITICAL**: `JWT_SECRET_KEY` must be **EXACTLY** the same as Auth API's secret.

### 2. Test Users Available

Auth API has 10 pre-configured test users ready to use:

```bash
# View credentials
cd /mnt/d/activity/auth-api
./test_oauth.sh --show-users
```

**Example test user:**
- Email: `grace.oauth@yahoo.com`
- Password: `OAuth!Testing321`
- Role: `oauth_client` (dedicated for OAuth testing)

See `auth-api/TEST_USERS_CREDENTIALS.md` for full list.

---

## 🔐 Implementation Guide

### Step 1: Install Dependencies

```bash
# For Python/FastAPI Image API
pip install pyjwt[crypto] httpx

# Add to requirements.txt
pyjwt[crypto]==2.8.0
httpx==0.26.0
```

### Step 2: Create Token Validation Utility

Create `app/core/oauth_validator.py`:

```python
"""
OAuth 2.0 Token Validation for Image API
Validates access tokens issued by Auth API's OAuth Authorization Server
"""

import jwt
from typing import Optional, Dict
from datetime import datetime, timezone
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Environment configuration
JWT_SECRET_KEY = "your-shared-secret"  # Must match Auth API
JWT_ALGORITHM = "HS256"
AUTH_API_URL = "http://auth-api:8000"

security = HTTPBearer()


class OAuthToken:
    """Parsed OAuth 2.0 access token"""

    def __init__(self, payload: Dict):
        self.user_id: str = payload.get("sub")
        self.client_id: str = payload.get("client_id")
        self.scopes: list = payload.get("scope", "").split()
        self.org_id: Optional[str] = payload.get("org_id")
        self.audience: list = payload.get("aud", [])
        self.issued_at: int = payload.get("iat")
        self.expires_at: int = payload.get("exp")
        self.jti: str = payload.get("jti")  # JWT ID (for revocation)

    def has_scope(self, required_scope: str) -> bool:
        """Check if token has required scope"""
        return required_scope in self.scopes

    def has_any_scope(self, *required_scopes: str) -> bool:
        """Check if token has any of the required scopes"""
        return any(scope in self.scopes for scope in required_scopes)

    def has_all_scopes(self, *required_scopes: str) -> bool:
        """Check if token has all required scopes"""
        return all(scope in self.scopes for scope in required_scopes)


def validate_oauth_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> OAuthToken:
    """
    Validate OAuth 2.0 access token from Authorization header.

    Usage in FastAPI route:
        @app.get("/protected")
        async def protected_route(token: OAuthToken = Depends(validate_oauth_token)):
            return {"user_id": token.user_id, "scopes": token.scopes}

    Raises:
        HTTPException: 401 if token invalid/expired, 403 if insufficient scope
    """
    token = credentials.credentials

    try:
        # Decode and validate JWT
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": True}  # Verify expiration
        )

        # Validate token type
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type (expected 'access' token)"
            )

        # Validate audience (optional - check if image-api is in audience)
        audience = payload.get("aud", [])
        if audience and "https://api.activity.com" not in audience:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token not intended for this service"
            )

        return OAuthToken(payload)

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )


def require_scope(*required_scopes: str):
    """
    Dependency factory for scope-based authorization.

    Usage:
        @app.post("/upload", dependencies=[Depends(require_scope("image:upload"))])
        async def upload_image(file: UploadFile):
            return {"image_id": "..."}
    """
    def scope_checker(token: OAuthToken = Depends(validate_oauth_token)) -> OAuthToken:
        if not token.has_all_scopes(*required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient scope. Required: {', '.join(required_scopes)}"
            )
        return token
    return scope_checker
```

### Step 3: Protect Image API Endpoints

```python
from fastapi import FastAPI, Depends, UploadFile, File
from app.core.oauth_validator import validate_oauth_token, require_scope, OAuthToken

app = FastAPI()


# Example 1: Upload image (requires image:upload scope)
@app.post("/api/v1/images/upload")
async def upload_image(
    file: UploadFile = File(...),
    token: OAuthToken = Depends(require_scope("image:upload"))
):
    """
    Upload an image.
    Requires 'image:upload' scope.
    """
    # Store image with user_id and org_id for ownership
    image_id = await store_image(
        file=file,
        user_id=token.user_id,
        org_id=token.org_id
    )

    return {
        "image_id": image_id,
        "user_id": token.user_id,
        "filename": file.filename
    }


# Example 2: Get user's images (requires image:read scope)
@app.get("/api/v1/images")
async def list_images(
    token: OAuthToken = Depends(require_scope("image:read"))
):
    """
    List all images for authenticated user.
    Requires 'image:read' scope.
    """
    images = await get_user_images(
        user_id=token.user_id,
        org_id=token.org_id
    )

    return {"images": images}


# Example 3: Get specific image (check ownership)
@app.get("/api/v1/images/{image_id}")
async def get_image(
    image_id: str,
    token: OAuthToken = Depends(require_scope("image:read"))
):
    """
    Get image by ID.
    Requires 'image:read' scope + ownership check.
    """
    image = await get_image_by_id(image_id)

    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Check ownership (user or organization)
    if image.user_id != token.user_id and image.org_id != token.org_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this image")

    return image


# Example 4: Delete image (requires image:delete scope)
@app.delete("/api/v1/images/{image_id}")
async def delete_image(
    image_id: str,
    token: OAuthToken = Depends(require_scope("image:delete"))
):
    """
    Delete image by ID.
    Requires 'image:delete' scope + ownership.
    """
    image = await get_image_by_id(image_id)

    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Check ownership
    if image.user_id != token.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this image")

    await delete_image_from_storage(image_id)

    return {"message": "Image deleted successfully"}


# Example 5: Organization images (org-scoped)
@app.get("/api/v1/organizations/{org_id}/images")
async def list_org_images(
    org_id: str,
    token: OAuthToken = Depends(require_scope("image:read"))
):
    """
    List all images for an organization.
    Requires 'image:read' scope + organization membership.
    """
    # Validate user has access to this organization
    if token.org_id != org_id:
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    images = await get_organization_images(org_id)

    return {"images": images, "organization_id": org_id}
```

---

## 🧪 Testing with Auth API

### 1. Get Access Token from Auth API

**Option A: Direct Login (Testing)**

```bash
# Login with test user
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "grace.oauth@yahoo.com",
    "password": "OAuth!Testing321"
  }'

# Response includes login code (email-based auth)
# For testing, you can extract user_id and generate token directly
```

**Option B: OAuth 2.0 Flow (Production)**

```bash
# Step 1: Generate PKCE challenge
CODE_VERIFIER=$(openssl rand -hex 32)
CODE_CHALLENGE=$(echo -n "$CODE_VERIFIER" | openssl dgst -binary -sha256 | base64 | tr '+/' '-_' | tr -d '=')

# Step 2: Get authorization code (user consent)
# Browser: http://localhost:8000/oauth/authorize?client_id=test-client-1&response_type=code&redirect_uri=http://localhost:3000/callback&scope=image:upload+image:read+image:delete&code_challenge=$CODE_CHALLENGE&code_challenge_method=S256&state=random123

# Step 3: Exchange code for tokens
curl -X POST http://localhost:8000/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "client_id=test-client-1" \
  -d "code=<authorization_code>" \
  -d "redirect_uri=http://localhost:3000/callback" \
  -d "code_verifier=$CODE_VERIFIER"

# Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "scope": "image:upload image:read image:delete"
}
```

### 2. Test Image API with Token

```bash
# Use access token from Auth API
ACCESS_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Upload image
curl -X POST http://localhost:8081/api/v1/images/upload \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F "file=@photo.jpg"

# List images
curl http://localhost:8081/api/v1/images \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# Get specific image
curl http://localhost:8081/api/v1/images/12345 \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# Delete image
curl -X DELETE http://localhost:8081/api/v1/images/12345 \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

---

## 📊 Available OAuth Scopes for Images

Auth API supports these scopes (configured for Image API):

### Image Management Scopes

- ✅ `image:upload` - Upload images
- ✅ `image:read` - View/download images
- ✅ `image:delete` - Delete images

These scopes are **already configured** in Auth API!

### Request Custom Scopes

If you need additional image-related scopes, you can request them to be added to Auth API:

```python
# Example custom scopes to request:
"image:edit" - Edit image metadata (title, description, tags)
"image:admin" - Full image management (all users/orgs)
"image:moderate" - Moderate user-uploaded images
"image:analytics" - View image analytics and statistics
```

---

## 🔄 Token Refresh Flow

Access tokens expire after 15 minutes. Use refresh tokens to get new access tokens:

```python
import httpx

async def refresh_access_token(refresh_token: str, client_id: str) -> dict:
    """
    Refresh access token using refresh token.

    Returns:
        dict with new access_token, refresh_token, expires_in
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{AUTH_API_URL}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id
            }
        )
        response.raise_for_status()
        return response.json()
```

---

## 🛡️ Security Considerations

### 1. Image Ownership Validation

**Always check ownership before operations:**

```python
async def verify_image_ownership(image_id: str, token: OAuthToken):
    """Verify user owns the image"""
    image = await get_image_by_id(image_id)

    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Check user ownership OR organization ownership
    if image.user_id != token.user_id and image.org_id != token.org_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    return image
```

### 2. File Upload Security

```python
from fastapi import UploadFile
import magic

ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

async def validate_upload(file: UploadFile):
    """Validate uploaded file"""
    # Check file size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    # Validate MIME type (use python-magic for real validation)
    mime = magic.from_buffer(contents, mime=True)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid file type: {mime}")

    # Reset file pointer
    await file.seek(0)
    return True
```

### 3. Organization Access Control

```python
async def verify_org_access(org_id: str, token: OAuthToken):
    """Verify user has access to organization"""
    if token.org_id != org_id:
        # Optionally: Check if user is member of organization
        is_member = await check_org_membership(token.user_id, org_id)
        if not is_member:
            raise HTTPException(
                status_code=403,
                detail="Not authorized for this organization"
            )
```

---

## 📖 Example: Complete Image Upload Flow

```python
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, status
from typing import Optional
import uuid
from datetime import datetime
from app.core.oauth_validator import validate_oauth_token, require_scope, OAuthToken

app = FastAPI()


class ImageMetadata:
    """Image metadata model"""
    def __init__(self, image_id: str, user_id: str, org_id: Optional[str],
                 filename: str, size: int, mime_type: str):
        self.image_id = image_id
        self.user_id = user_id
        self.org_id = org_id
        self.filename = filename
        self.size = size
        self.mime_type = mime_type
        self.uploaded_at = datetime.utcnow()


@app.post("/api/v1/images/upload", status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    title: Optional[str] = None,
    description: Optional[str] = None,
    token: OAuthToken = Depends(require_scope("image:upload"))
):
    """
    Upload an image with metadata.

    Security:
        - Validates OAuth 2.0 access token
        - Requires 'image:upload' scope
        - Validates file type and size
        - Associates image with user/organization

    Args:
        file: Image file (JPEG, PNG, GIF, WebP)
        title: Optional image title
        description: Optional image description
        token: OAuth token (injected by dependency)

    Returns:
        Image metadata with upload confirmation
    """
    # Validate file
    contents = await file.read()

    # Check file size (10 MB max)
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 10MB)"
        )

    # Validate MIME type
    import magic
    mime_type = magic.from_buffer(contents, mime=True)
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]

    if mime_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {mime_type}. Allowed: {', '.join(allowed_types)}"
        )

    # Generate unique image ID
    image_id = str(uuid.uuid4())

    # Store image in storage (S3, local filesystem, etc.)
    storage_path = await store_image_file(image_id, contents, mime_type)

    # Save metadata to database
    metadata = ImageMetadata(
        image_id=image_id,
        user_id=token.user_id,
        org_id=token.org_id,
        filename=file.filename,
        size=len(contents),
        mime_type=mime_type
    )

    await save_image_metadata(metadata, title, description)

    # Return success response
    return {
        "image_id": image_id,
        "filename": file.filename,
        "size": len(contents),
        "mime_type": mime_type,
        "user_id": token.user_id,
        "organization_id": token.org_id,
        "uploaded_at": metadata.uploaded_at.isoformat(),
        "storage_path": storage_path
    }


@app.get("/api/v1/images/{image_id}")
async def get_image(
    image_id: str,
    token: OAuthToken = Depends(require_scope("image:read"))
):
    """Get image metadata and download URL"""
    # Verify ownership
    image = await verify_image_ownership(image_id, token)

    # Generate temporary download URL (if using S3)
    download_url = await generate_download_url(image_id, expires_in=3600)

    return {
        "image_id": image.image_id,
        "filename": image.filename,
        "download_url": download_url,
        "user_id": image.user_id,
        "organization_id": image.org_id
    }
```

---

## 🧪 Testing Checklist

Before integrating OAuth 2.0:

- [ ] `JWT_SECRET_KEY` matches Auth API
- [ ] `JWT_ALGORITHM` set to `HS256`
- [ ] `AUTH_API_URL` points to Auth API
- [ ] Token validation utility implemented
- [ ] Protected endpoints use `Depends(validate_oauth_token)`
- [ ] Scope checks for image:upload, image:read, image:delete
- [ ] Test with Auth API test users (grace.oauth@yahoo.com)
- [ ] Test image upload with valid token
- [ ] Test image access with ownership check
- [ ] Test token expiration (wait 15 minutes)
- [ ] Test invalid token (modified JWT)
- [ ] Test missing/wrong scope (403 response)
- [ ] Test refresh token flow

---

## 📚 Additional Resources

### Auth API Documentation

- **OAuth Implementation**: `/mnt/d/activity/auth-api/OAUTH_IMPLEMENTATION.md`
- **Test Users**: `/mnt/d/activity/auth-api/TEST_USERS_CREDENTIALS.md`
- **Test Suite**: `/mnt/d/activity/auth-api/test_oauth.sh --help`

### Testing OAuth Flows

```bash
cd /mnt/d/activity/auth-api

# Show test users
./test_oauth.sh --show-users

# Run OAuth test suite
./test_oauth.sh

# Setup test users
./test_oauth.sh --setup-users
```

---

## 🆘 Troubleshooting

### Issue: "Invalid token signature"

**Cause**: `JWT_SECRET_KEY` doesn't match between Auth API and Image API

**Solution**:
```bash
# Check Auth API secret
docker exec auth-api env | grep JWT_SECRET_KEY

# Update Image API .env to match
JWT_SECRET_KEY=<same-as-auth-api>
```

### Issue: "Token has expired"

**Cause**: Access token expired (15 min lifetime)

**Solution**: Use refresh token to get new access token

### Issue: "Insufficient scope"

**Cause**: Token doesn't have required image scope

**Solution**: Request `image:upload`, `image:read`, or `image:delete` scopes during OAuth authorization flow

### Issue: "Not authorized to access this image"

**Cause**: User doesn't own the image

**Solution**: Verify image ownership in database (user_id or org_id match)

---

## ✅ Quick Start Checklist

1. [ ] Copy `JWT_SECRET_KEY` from Auth API to Image API `.env`
2. [ ] Set `JWT_ALGORITHM=HS256` in Image API `.env`
3. [ ] Install dependencies: `pip install pyjwt[crypto] httpx python-magic`
4. [ ] Copy `oauth_validator.py` to `app/core/`
5. [ ] Update protected endpoints to use `Depends(validate_oauth_token)`
6. [ ] Add ownership checks for image operations
7. [ ] Test with Auth API test user (grace.oauth@yahoo.com)
8. [ ] Verify 401 for invalid tokens
9. [ ] Verify 403 for insufficient scopes
10. [ ] Verify 403 for unauthorized image access

---

**Ready to integrate! 🚀**

Questions? Check Auth API's comprehensive test suite and documentation.

**Created by:** Claude Code
**Auth API Status:** ✅ Production Ready (23/23 tests passing)
**Last Updated:** 2025-11-12
