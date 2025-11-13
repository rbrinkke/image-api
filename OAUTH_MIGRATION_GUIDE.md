# OAuth 2.0 Migration Guide for Image-API

**Target Audience:** AI Agent
**Objective:** Migrate image-api from basic authentication to OAuth 2.0 with multi-tenant support
**Success Criteria:** Users can upload/retrieve images with OAuth tokens, multi-tenant isolation verified in MongoDB

---

## Prerequisites - Verify Before Starting

```bash
# 1. Verify auth-api is running
curl http://localhost:8000/health
# Expected: {"status":"healthy"}

# 2. Verify test users exist
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice.admin@example.com","password":"SecurePass123!Admin"}'
# Expected: Returns access_token

# 3. Verify MongoDB is accessible
docker exec image-api-mongodb mongosh --quiet --eval "db.version()"
# Expected: MongoDB version number
```

If any prerequisite fails, STOP and resolve before continuing.

---

## Phase 1: Register OAuth Client in Auth-API

### Step 1.1: Check if client exists
```bash
docker exec auth-db psql -U postgres -d activitydb -c \
  "SELECT client_id FROM activity.oauth_clients WHERE client_id = 'image-api-service';"
```

**Expected Output:** Empty (client doesn't exist yet)

### Step 1.2: Register image-api-service client
```bash
docker exec auth-db psql -U postgres -d activitydb -c \
  "INSERT INTO activity.oauth_clients (client_id, client_secret, client_name, redirect_uris, grant_types, scopes, is_active)
   VALUES (
     'image-api-service',
     'your-image-service-secret-change-in-production',
     'Image API Service',
     '{}',
     ARRAY['client_credentials'],
     ARRAY['users:read', 'organizations:read'],
     true
   );"
```

**Expected Output:** `INSERT 0 1`

### Step 1.3: Verify registration
```bash
curl -X POST http://localhost:8000/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=image-api-service&client_secret=your-image-service-secret-change-in-production&scope=users:read organizations:read"
```

**Expected Output:** JSON with `access_token` field
**Verification:** Decode token and verify `sub: "image-api-service"`
```bash
# Extract and decode token payload
TOKEN="<paste_access_token_here>"
echo $TOKEN | cut -d'.' -f2 | base64 -d | jq '.'
# Expected: {"sub":"image-api-service","client_id":"image-api-service","scope":"users:read organizations:read",...}
```

**CRITICAL:** If token doesn't have `sub` field or sub != "image-api-service", auth-api needs fixing (see auth-api/app/routes/oauth_token.py line 519).

---

## Phase 2: Add OAuth Dependencies

### Step 2.1: Update requirements.txt
```bash
cd /mnt/d/activity/image-api
```

Add these dependencies to `requirements.txt`:
```
python-jose[cryptography]==3.3.0
python-multipart==0.0.6
```

### Step 2.2: Install dependencies
```bash
pip install -r requirements.txt
```

**Verification:**
```bash
python -c "from jose import jwt; print('jose imported successfully')"
```
**Expected Output:** `jose imported successfully`

---

## Phase 3: Create OAuth Validator

### Step 3.1: Copy oauth_validator.py from chat-api
```bash
cp /mnt/d/activity/chat-api/app/core/oauth_validator.py \
   /mnt/d/activity/image-api/app/core/oauth_validator.py
```

### Step 3.2: Update imports for image-api
Edit `/mnt/d/activity/image-api/app/core/oauth_validator.py`:

Change:
```python
from app.config import settings
```

Verify settings has these fields:
```python
# app/config.py
class Settings(BaseSettings):
    JWT_SECRET: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    AUTH_API_URL: str = "http://auth-api:8000"
```

### Step 3.3: Create dependency function
Add to `/mnt/d/activity/image-api/app/dependencies.py`:

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.oauth_validator import validate_token

security = HTTPBearer()

async def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Extracts and validates OAuth token.
    Returns principal: {type, user_id, org_id, client_id, scopes}
    """
    token = credentials.credentials
    principal = await validate_token(token)
    return principal

async def get_current_user(principal: dict = Depends(get_current_principal)) -> dict:
    """
    Requires user token (not service token).
    Returns user principal with user_id and org_id.
    """
    if principal["type"] != "user":
        raise HTTPException(status_code=403, detail="User token required")
    return principal

async def get_service_principal(principal: dict = Depends(get_current_principal)) -> dict:
    """
    Requires service token.
    Returns service principal with client_id.
    """
    if principal["type"] != "service":
        raise HTTPException(status_code=403, detail="Service token required")
    return principal
```

**Verification:**
```bash
python -c "from app.dependencies import get_current_principal; print('Dependencies loaded')"
```

---

## Phase 4: Update Data Models

### Step 4.1: Add multi-tenant fields to Image model

Edit `/mnt/d/activity/image-api/app/models/image.py`:

```python
from beanie import Document
from datetime import datetime
from typing import Optional

class Image(Document):
    # Multi-tenant fields (NEW)
    org_id: str  # Organization ID from token
    user_id: str  # Owner user ID from token

    # Existing fields
    filename: str
    content_type: str
    size: int
    storage_path: str

    # Visibility control (NEW)
    visibility: str = "private"  # private | org | public

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Settings:
        name = "images"
        indexes = [
            "org_id",
            "user_id",
            [("org_id", 1), ("user_id", 1)],  # Compound index for queries
            [("org_id", 1), ("visibility", 1)]
        ]
```

### Step 4.2: Create MongoDB indexes
```bash
docker exec image-api-mongodb mongosh image_db --eval '
db.images.createIndex({org_id: 1});
db.images.createIndex({user_id: 1});
db.images.createIndex({org_id: 1, user_id: 1});
db.images.createIndex({org_id: 1, visibility: 1});
'
```

**Verification:**
```bash
docker exec image-api-mongodb mongosh image_db --eval 'db.images.getIndexes()'
```
**Expected:** Shows all 4 indexes created

---

## Phase 5: Update Routes with OAuth

### Step 5.1: Update upload endpoint

Edit `/mnt/d/activity/image-api/app/routes/images.py`:

```python
from fastapi import APIRouter, Depends, UploadFile, File, Form
from app.dependencies import get_current_user
from app.models.image import Image
from datetime import datetime

router = APIRouter()

@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    visibility: str = Form("private"),
    principal: dict = Depends(get_current_user)  # NEW: OAuth dependency
):
    """Upload image with OAuth authentication."""

    # Extract user info from OAuth token
    user_id = principal["user_id"]
    org_id = principal["org_id"]

    # Validate visibility
    if visibility not in ["private", "org", "public"]:
        raise HTTPException(status_code=400, detail="Invalid visibility")

    # Store file (existing logic)
    storage_path = f"uploads/{org_id}/{user_id}/{file.filename}"
    # ... file storage code ...

    # Create image record with multi-tenant fields
    image = Image(
        org_id=org_id,  # NEW
        user_id=user_id,  # NEW
        filename=file.filename,
        content_type=file.content_type,
        size=file.size,
        storage_path=storage_path,
        visibility=visibility,  # NEW
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    await image.insert()

    return {
        "id": str(image.id),
        "filename": image.filename,
        "visibility": image.visibility,
        "created_at": image.created_at
    }
```

### Step 5.2: Update list images endpoint

```python
@router.get("/")
async def list_images(
    principal: dict = Depends(get_current_user)
):
    """List user's images with multi-tenant isolation."""

    user_id = principal["user_id"]
    org_id = principal["org_id"]

    # Query: user's own images OR org-visible images in same org
    images = await Image.find(
        {
            "$or": [
                {"user_id": user_id, "org_id": org_id},  # Own images
                {"visibility": "org", "org_id": org_id}   # Org-shared
            ]
        }
    ).to_list()

    return images
```

### Step 5.3: Update get image endpoint

```python
@router.get("/{image_id}")
async def get_image(
    image_id: str,
    principal: dict = Depends(get_current_user)
):
    """Get image with authorization check."""

    from bson import ObjectId

    image = await Image.get(ObjectId(image_id))
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Authorization check
    user_id = principal["user_id"]
    org_id = principal["org_id"]

    # Access allowed if:
    # 1. User owns the image
    # 2. Image is org-visible and user is in same org
    # 3. Image is public
    if image.user_id == user_id:
        return image
    elif image.visibility == "org" and image.org_id == org_id:
        return image
    elif image.visibility == "public":
        return image
    else:
        raise HTTPException(status_code=403, detail="Access denied")
```

### Step 5.4: Add service endpoint for cleanup

```python
from app.dependencies import get_service_principal

@router.delete("/cleanup")
async def cleanup_old_images(
    days: int = 30,
    principal: dict = Depends(get_service_principal)  # Service token only
):
    """Cleanup images older than N days (admin operation)."""

    from datetime import timedelta

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Service tokens can access all images across all orgs
    old_images = await Image.find(
        {"created_at": {"$lt": cutoff_date}}
    ).to_list()

    deleted_count = 0
    for image in old_images:
        await image.delete()
        deleted_count += 1

    return {
        "deleted_count": deleted_count,
        "cutoff_date": cutoff_date
    }
```

---

## Phase 6: Update Environment Configuration

### Step 6.1: Update .env file

Add these variables to `/mnt/d/activity/image-api/.env`:

```bash
# OAuth Configuration (MUST match auth-api)
JWT_SECRET="your-secret-key-change-in-production"
JWT_ALGORITHM="HS256"
AUTH_API_URL="http://auth-api:8000"

# Service Client Credentials
IMAGE_SERVICE_CLIENT_ID="image-api-service"
IMAGE_SERVICE_CLIENT_SECRET="your-image-service-secret-change-in-production"
IMAGE_SERVICE_SCOPES="users:read organizations:read"

# API Configuration
PORT=8002
```

### Step 6.2: Update config.py

Edit `/mnt/d/activity/image-api/app/config.py`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # OAuth settings
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    AUTH_API_URL: str = "http://auth-api:8000"

    # Service client
    IMAGE_SERVICE_CLIENT_ID: str = "image-api-service"
    IMAGE_SERVICE_CLIENT_SECRET: str
    IMAGE_SERVICE_SCOPES: str = "users:read organizations:read"

    # API settings
    PORT: int = 8002

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## Phase 7: Rebuild and Deploy

### Step 7.1: Stop existing container
```bash
cd /mnt/d/activity/image-api
docker compose stop image-api
```

### Step 7.2: Rebuild with --no-cache (CRITICAL)
```bash
docker compose build --no-cache image-api
```

**WHY --no-cache:** Docker caches old code. Without --no-cache, OAuth changes won't be applied.

### Step 7.3: Start container
```bash
docker compose up -d image-api
```

### Step 7.4: Verify startup
```bash
docker logs image-api --tail 20
```

**Expected:** No errors, shows "Application startup complete"

---

## Phase 8: Testing and Verification

### Step 8.1: Get test user tokens

```bash
# Alice login
ALICE_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice.admin@example.com","password":"SecurePass123!Admin","org_id":"f9aafe3b-9df3-4b29-9ae6-4f135c214fb0"}')

ALICE_TOKEN=$(echo $ALICE_RESPONSE | jq -r '.access_token')
echo "Alice Token: $ALICE_TOKEN"

# Bob login
BOB_RESPONSE=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"bob.developer@example.com","password":"DevSecure2024!Bob","org_id":"f9aafe3b-9df3-4b29-9ae6-4f135c214fb0"}')

BOB_TOKEN=$(echo $BOB_RESPONSE | jq -r '.access_token')
echo "Bob Token: $BOB_TOKEN"
```

### Step 8.2: Test image upload

```bash
# Create test image
echo "Test image content" > /tmp/test_image.jpg

# Alice uploads private image
ALICE_UPLOAD=$(curl -s -X POST http://localhost:8002/api/images/upload \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -F "file=@/tmp/test_image.jpg" \
  -F "visibility=private")

echo "Alice Upload Response:"
echo $ALICE_UPLOAD | jq '.'

ALICE_IMAGE_ID=$(echo $ALICE_UPLOAD | jq -r '.id')
```

**Expected:** Returns image object with `id`, `filename`, `visibility: "private"`

### Step 8.3: Verify in MongoDB

```bash
docker exec image-api-mongodb mongosh image_db --eval "
db.images.findOne({_id: ObjectId('$ALICE_IMAGE_ID')})
"
```

**Expected Output:**
```json
{
  _id: ObjectId('...'),
  org_id: 'f9aafe3b-9df3-4b29-9ae6-4f135c214fb0',
  user_id: '4c52f4f6-6afe-4203-8761-9d30f0382695',
  filename: 'test_image.jpg',
  visibility: 'private',
  ...
}
```

**Verification Checklist:**
- ✅ org_id matches Alice's org
- ✅ user_id matches Alice's user ID
- ✅ visibility is "private"

### Step 8.4: Test multi-tenant isolation

```bash
# Bob tries to access Alice's private image
BOB_ACCESS=$(curl -s -X GET http://localhost:8002/api/images/$ALICE_IMAGE_ID \
  -H "Authorization: Bearer $BOB_TOKEN")

echo "Bob Access Response:"
echo $BOB_ACCESS | jq '.'
```

**Expected:** `{"detail":"Access denied"}` with status 403

**WHY:** Image is private (visibility="private") and Bob is not the owner (different user_id).

### Step 8.5: Test org-shared images

```bash
# Alice uploads org-shared image
ALICE_ORG_IMAGE=$(curl -s -X POST http://localhost:8002/api/images/upload \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -F "file=@/tmp/test_image.jpg" \
  -F "visibility=org")

ORG_IMAGE_ID=$(echo $ALICE_ORG_IMAGE | jq -r '.id')

# Bob accesses org-shared image (same org)
BOB_ORG_ACCESS=$(curl -s -X GET http://localhost:8002/api/images/$ORG_IMAGE_ID \
  -H "Authorization: Bearer $BOB_TOKEN")

echo "Bob Org Access Response:"
echo $BOB_ORG_ACCESS | jq '.'
```

**Expected:** Returns image object with status 200
**WHY:** Image has visibility="org" and Bob is in same org_id

### Step 8.6: Test service token

```bash
# Get service token
SERVICE_TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=image-api-service&client_secret=your-image-service-secret-change-in-production&scope=users:read organizations:read" \
  | jq -r '.access_token')

# Service cleanup (admin operation)
CLEANUP=$(curl -s -X DELETE "http://localhost:8002/api/images/cleanup?days=365" \
  -H "Authorization: Bearer $SERVICE_TOKEN")

echo "Cleanup Response:"
echo $CLEANUP | jq '.'
```

**Expected:** Returns `{"deleted_count": N, "cutoff_date": "..."}`
**WHY:** Service tokens bypass org restrictions for admin operations

### Step 8.7: Final MongoDB verification

```bash
# Count images by org and user
docker exec image-api-mongodb mongosh image_db --eval "
db.images.aggregate([
  {
    \$group: {
      _id: { org_id: '\$org_id', user_id: '\$user_id' },
      count: { \$sum: 1 }
    }
  }
])
"
```

**Expected:** Shows image counts grouped by org_id and user_id

---

## Success Criteria Checklist

Before marking migration complete, verify ALL of these:

- [ ] OAuth client "image-api-service" registered in auth-api
- [ ] Service token acquisition works (returns access_token with sub="image-api-service")
- [ ] User tokens work (Alice and Bob can login)
- [ ] Image upload adds org_id and user_id to MongoDB
- [ ] MongoDB indexes created on org_id, user_id
- [ ] Multi-tenant isolation verified (Bob cannot access Alice's private images)
- [ ] Org-shared images accessible within same org
- [ ] Service token cleanup endpoint works
- [ ] Docker container rebuilt with --no-cache
- [ ] No errors in `docker logs image-api`
- [ ] All test scenarios PASS

---

## Troubleshooting

### Issue: "Invalid token" error

**Diagnosis:**
```bash
# Check token structure
echo $ALICE_TOKEN | cut -d'.' -f2 | base64 -d | jq '.'
```

**Fix:** Verify JWT_SECRET matches between image-api and auth-api .env files

---

### Issue: "Access denied" for valid user

**Diagnosis:**
```bash
# Check image org_id and user's org_id
docker exec image-api-mongodb mongosh image_db --eval "
db.images.findOne({_id: ObjectId('$IMAGE_ID')}, {org_id: 1, user_id: 1, visibility: 1})
"
```

**Fix:** Ensure user is member of image's org_id in auth-api

---

### Issue: Changes not applied after code edit

**Diagnosis:** Docker is running old cached image

**Fix:**
```bash
docker compose stop image-api
docker compose build --no-cache image-api
docker compose up -d image-api
```

**NEVER skip --no-cache flag**

---

## Next Steps After Migration

1. Update frontend to use OAuth tokens
2. Add image deletion with auth checks
3. Add image update/metadata endpoints
4. Implement file storage cleanup service
5. Add monitoring and logging for OAuth events

---

**Migration Status:** Ready for execution
**Estimated Time:** 2-3 hours
**Risk Level:** Medium (requires careful testing)
**Rollback Plan:** Revert to previous image-api version via git
