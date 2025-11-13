# OAuth Testing Credentials for Image-API

**Purpose:** Reference document for OAuth testing with verified credentials
**Last Updated:** 2025-11-13
**Status:** ✅ Verified Working

---

## Test Organization

**Organization ID:** `f9aafe3b-9df3-4b29-9ae6-4f135c214fb0`
**Organization Name:** Demo Organization
**Created By:** alice.admin@example.com

---

## Test Users

### Alice Admin (Primary Test User)

**Credentials:**
- Email: `alice.admin@example.com`
- Password: `SecurePass123!Admin`
- User ID: `4c52f4f6-6afe-4203-8761-9d30f0382695`
- Organization: `f9aafe3b-9df3-4b29-9ae6-4f135c214fb0`
- Role: `owner`

**Login Command:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice.admin@example.com",
    "password": "SecurePass123!Admin",
    "org_id": "f9aafe3b-9df3-4b29-9ae6-4f135c214fb0"
  }'
```

**Expected Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "org_id": "f9aafe3b-9df3-4b29-9ae6-4f135c214fb0"
}
```

**Token Claims:**
```json
{
  "sub": "4c52f4f6-6afe-4203-8761-9d30f0382695",
  "type": "access",
  "org_id": "f9aafe3b-9df3-4b29-9ae6-4f135c214fb0",
  "exp": 1763016472
}
```

**Use Cases:**
- Primary user for image upload tests
- Owner permissions testing
- Multi-tenant isolation verification

---

### Bob Developer (Secondary Test User)

**Credentials:**
- Email: `bob.developer@example.com`
- Password: `DevSecure2024!Bob`
- User ID: `5b6b84b5-01fe-46b1-827a-ed23548ac59c`
- Organization: `f9aafe3b-9df3-4b29-9ae6-4f135c214fb0`
- Role: `member`

**Login Command:**
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "bob.developer@example.com",
    "password": "DevSecure2024!Bob",
    "org_id": "f9aafe3b-9df3-4b29-9ae6-4f135c214fb0"
  }'
```

**Token Claims:**
```json
{
  "sub": "5b6b84b5-01fe-46b1-827a-ed23548ac59c",
  "type": "access",
  "org_id": null,
  "exp": 1763016922
}
```

**IMPORTANT:** Bob needs to be added to organization first!

**Add Bob to Organization:**
```sql
-- Run in auth-api database
INSERT INTO activity.organization_members (organization_id, user_id, role, added_by)
VALUES (
  'f9aafe3b-9df3-4b29-9ae6-4f135c214fb0',
  '5b6b84b5-01fe-46b1-827a-ed23548ac59c',
  'member',
  '4c52f4f6-6afe-4203-8761-9d30f0382695'
)
ON CONFLICT DO NOTHING;
```

**Use Cases:**
- Test access denial (cannot access Alice's private images)
- Test org-shared image access (same org as Alice)
- Member-level permissions testing

---

## Service Client

**Client Registration:**
- Client ID: `image-api-service`
- Client Secret: `your-image-service-secret-change-in-production`
- Grant Types: `client_credentials`
- Scopes: `users:read organizations:read`

**Registration Command:**
```sql
-- Run in auth-api database
INSERT INTO activity.oauth_clients
  (client_id, client_secret, client_name, redirect_uris, grant_types, scopes, is_active)
VALUES (
  'image-api-service',
  'your-image-service-secret-change-in-production',
  'Image API Service',
  '{}',
  ARRAY['client_credentials'],
  ARRAY['users:read', 'organizations:read'],
  true
)
ON CONFLICT (client_id) DO NOTHING;
```

**Get Service Token:**
```bash
curl -X POST http://localhost:8000/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=image-api-service&client_secret=your-image-service-secret-change-in-production&scope=users:read organizations:read"
```

**Expected Service Token Claims:**
```json
{
  "sub": "image-api-service",
  "client_id": "image-api-service",
  "scope": "users:read organizations:read",
  "type": "access",
  "aud": ["https://api.activity.com"],
  "exp": 1763016205
}
```

**Use Cases:**
- Admin cleanup operations
- Cross-org data access
- Maintenance tasks

---

## Quick Test Script

```bash
#!/bin/bash

# Get Alice token
ALICE_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice.admin@example.com","password":"SecurePass123!Admin","org_id":"f9aafe3b-9df3-4b29-9ae6-4f135c214fb0"}' \
  | jq -r '.access_token')

echo "Alice Token: $ALICE_TOKEN"

# Decode token to verify
echo $ALICE_TOKEN | cut -d'.' -f2 | base64 -d | jq '.'

# Get Bob token
BOB_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"bob.developer@example.com","password":"DevSecure2024!Bob","org_id":"f9aafe3b-9df3-4b29-9ae6-4f135c214fb0"}' \
  | jq -r '.access_token')

echo "Bob Token: $BOB_TOKEN"

# Get Service token
SERVICE_TOKEN=$(curl -s -X POST http://localhost:8000/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=image-api-service&client_secret=your-image-service-secret-change-in-production&scope=users:read organizations:read" \
  | jq -r '.access_token')

echo "Service Token: $SERVICE_TOKEN"

# Verify service token sub claim
echo $SERVICE_TOKEN | cut -d'.' -f2 | base64 -d | jq '.sub'
# Expected: "image-api-service"
```

---

## Test Scenarios

### Scenario 1: Upload and Retrieve Own Image

```bash
# Alice uploads image
curl -X POST http://localhost:8002/api/images/upload \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -F "file=@test.jpg" \
  -F "visibility=private"

# Expected: Returns image object with Alice's user_id and org_id

# Alice retrieves her images
curl -X GET http://localhost:8002/api/images \
  -H "Authorization: Bearer $ALICE_TOKEN"

# Expected: Array containing Alice's image
```

### Scenario 2: Access Denial (Multi-Tenant Isolation)

```bash
# Alice uploads private image
ALICE_IMAGE=$(curl -s -X POST http://localhost:8002/api/images/upload \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -F "file=@test.jpg" \
  -F "visibility=private")

IMAGE_ID=$(echo $ALICE_IMAGE | jq -r '.id')

# Bob tries to access Alice's private image
curl -X GET http://localhost:8002/api/images/$IMAGE_ID \
  -H "Authorization: Bearer $BOB_TOKEN"

# Expected: {"detail":"Access denied"} with status 403
```

### Scenario 3: Org-Shared Images

```bash
# Alice uploads org-shared image
ALICE_ORG_IMAGE=$(curl -s -X POST http://localhost:8002/api/images/upload \
  -H "Authorization: Bearer $ALICE_TOKEN" \
  -F "file=@logo.png" \
  -F "visibility=org")

ORG_IMAGE_ID=$(echo $ALICE_ORG_IMAGE | jq -r '.id')

# Bob accesses org-shared image (same org)
curl -X GET http://localhost:8002/api/images/$ORG_IMAGE_ID \
  -H "Authorization: Bearer $BOB_TOKEN"

# Expected: Returns image object (Bob is in same org)
```

### Scenario 4: Service Token Admin Operations

```bash
# Service cleanup old images
curl -X DELETE "http://localhost:8002/api/images/cleanup?days=30" \
  -H "Authorization: Bearer $SERVICE_TOKEN"

# Expected: {"deleted_count": N, "cutoff_date": "..."}
```

---

## MongoDB Verification Queries

### Check Image Multi-Tenancy

```bash
docker exec image-api-mongodb mongosh image_db --eval '
db.images.find({}, {org_id: 1, user_id: 1, filename: 1, visibility: 1}).pretty()
'
```

**Expected:** All images have `org_id` and `user_id` fields

### Count Images by User

```bash
docker exec image-api-mongodb mongosh image_db --eval '
db.images.aggregate([
  {
    $group: {
      _id: {org_id: "$org_id", user_id: "$user_id"},
      count: {$sum: 1}
    }
  }
])
'
```

### Verify Isolation

```bash
# Alice's images
docker exec image-api-mongodb mongosh image_db --eval '
db.images.countDocuments({
  org_id: "f9aafe3b-9df3-4b29-9ae6-4f135c214fb0",
  user_id: "4c52f4f6-6afe-4203-8761-9d30f0382695"
})
'

# Bob's images
docker exec image-api-mongodb mongosh image_db --eval '
db.images.countDocuments({
  org_id: "f9aafe3b-9df3-4b29-9ae6-4f135c214fb0",
  user_id: "5b6b84b5-01fe-46b1-827a-ed23548ac59c"
})
'
```

---

## Token Debugging

### Decode Token Manually

```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Extract header
echo $TOKEN | cut -d'.' -f1 | base64 -d | jq '.'

# Extract payload
echo $TOKEN | cut -d'.' -f2 | base64 -d | jq '.'

# Check expiration
echo $TOKEN | cut -d'.' -f2 | base64 -d | jq '.exp'
# Compare with current timestamp: date +%s
```

### Verify Token Type

```bash
# User token
echo $ALICE_TOKEN | cut -d'.' -f2 | base64 -d | jq '{sub, type, org_id}'
# Expected: sub is UUID, type="access", org_id present

# Service token
echo $SERVICE_TOKEN | cut -d'.' -f2 | base64 -d | jq '{sub, type, client_id}'
# Expected: sub="image-api-service", type="access", client_id="image-api-service"
```

---

## Troubleshooting

### "Invalid credentials" on login

**Cause:** User password incorrect or user doesn't exist

**Fix:**
```bash
# Verify user exists in auth-api
docker exec auth-db psql -U postgres -d activitydb -c \
  "SELECT email, is_verified FROM activity.users WHERE email = 'alice.admin@example.com';"
```

### "Invalid token" on API request

**Cause:** JWT_SECRET mismatch or token expired

**Fix:**
```bash
# Check token expiration
echo $ALICE_TOKEN | cut -d'.' -f2 | base64 -d | jq '.exp'
CURRENT_TIME=$(date +%s)
echo "Current: $CURRENT_TIME"

# Get fresh token if expired
```

### Bob has no org_id in token

**Cause:** Bob is not a member of any organization

**Fix:**
```bash
# Add Bob to Demo Organization
docker exec auth-db psql -U postgres -d activitydb -c \
  "INSERT INTO activity.organization_members (organization_id, user_id, role, added_by)
   VALUES ('f9aafe3b-9df3-4b29-9ae6-4f135c214fb0', '5b6b84b5-01fe-46b1-827a-ed23548ac59c', 'member', '4c52f4f6-6afe-4203-8761-9d30f0382695')
   ON CONFLICT DO NOTHING;"

# Login again to get token with org_id
```

---

## Environment Variables Reference

**image-api/.env:**
```bash
# MUST match auth-api JWT_SECRET exactly
JWT_SECRET="your-secret-key-change-in-production"
JWT_ALGORITHM="HS256"

# Auth-API connection
AUTH_API_URL="http://auth-api:8000"

# Service client credentials
IMAGE_SERVICE_CLIENT_ID="image-api-service"
IMAGE_SERVICE_CLIENT_SECRET="your-image-service-secret-change-in-production"
IMAGE_SERVICE_SCOPES="users:read organizations:read"
```

---

**Status:** ✅ All credentials verified working
**Last Tested:** 2025-11-13
**Used In:** chat-api OAuth migration (100% successful)
