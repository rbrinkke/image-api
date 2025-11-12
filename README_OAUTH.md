# OAuth 2.0 Integration - Image API

**Status:** ✅ Auth API Ready | 📖 Integration Guide Available

---

## 🎯 What You Need to Know

Auth API has a **fully working OAuth 2.0 Authorization Server** (23/23 tests passing).

Image API can authenticate users by **validating JWT tokens** issued by Auth API.

**Token Type:** HS256 (shared secret) - **No JWKS endpoint needed**

---

## 📁 Documentation Files

| File | Purpose |
|------|---------|
| `OAUTH_QUICK_START.md` | ⚡ 5-minute setup guide |
| `OAUTH_INTEGRATION_GUIDE.md` | 📚 Complete implementation guide |
| `../auth-api/TEST_USERS_CREDENTIALS.md` | 👥 10 test users with passwords |
| `../auth-api/OAUTH_IMPLEMENTATION.md` | 🔐 Auth API OAuth details |

---

## ⚡ Quick Start

```bash
# 1. Copy JWT secret from Auth API
JWT_SECRET_KEY=<auth-api-secret>

# 2. Install package
pip install pyjwt[crypto]

# 3. Validate tokens
import jwt
payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
user_id = payload["sub"]
scopes = payload["scope"].split()
```

**That's it!** No JWKS, no RS256, no public keys needed. ✅

---

## 👥 Test Users

10 pre-configured test users available in Auth API:

```bash
cd /mnt/d/activity/auth-api
./test_oauth.sh --show-users
```

**Example:**
- Email: `grace.oauth@yahoo.com`
- Password: `OAuth!Testing321`
- Role: OAuth testing

---

## 🔑 Token Structure

```json
{
  "iss": "http://localhost:8000",
  "sub": "user-uuid",
  "aud": ["https://api.activity.com"],
  "exp": 1699999999,
  "iat": 1699999000,
  "jti": "token-id",
  "type": "access",
  "scope": "image:read image:upload image:delete",
  "client_id": "image-api",
  "azp": "image-api",
  "org_id": "org-uuid"
}
```

---

## 🖼️ Image-Specific Scopes

| Scope | Description |
|-------|-------------|
| `image:read` | View images |
| `image:upload` | Upload new images |
| `image:delete` | Delete images |
| `image:write` | Create/update image metadata |
| `admin` | Full admin access |

---

## ✅ Integration Checklist

- [ ] Read `OAUTH_QUICK_START.md`
- [ ] Copy `JWT_SECRET_KEY` from Auth API
- [ ] Implement token validation
- [ ] Test with test user (grace.oauth@yahoo.com)
- [ ] Add scope checks for image operations
- [ ] Add ownership validation (users can only access their own images)
- [ ] Implement file upload security
- [ ] Read full guide: `OAUTH_INTEGRATION_GUIDE.md`

---

## 🛡️ Security Considerations

**Image API has unique security needs:**
- ✅ **Ownership Validation**: Users can only access their own images
- ✅ **File Upload Security**: Validate file types, sizes, scan for malware
- ✅ **Scope Enforcement**: Require correct scopes for each operation
- ✅ **Organization Access**: Respect org_id from token for multi-tenant support

---

## 🆘 Questions?

1. Read `OAUTH_INTEGRATION_GUIDE.md` (comprehensive)
2. Check Auth API test suite: `./test_oauth.sh`
3. View test users: `./test_oauth.sh --show-users`

---

**Auth API OAuth Status:** ✅ Production Ready (23/23 tests passing)
**Last Updated:** 2025-11-12
