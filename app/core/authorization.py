"""
OAuth 2.0 Resource Server Authorization
========================================

The image-api now operates as a pure OAuth 2.0 Resource Server.

Architecture Changes:
--------------------
BEFORE (Distributed Authorization System):
- JWT contained minimal claims (user_id, org_id)
- Made HTTP calls to auth-api for permission checks
- Used Redis cache layer with TTL
- Circuit breaker pattern for resilience
- Complex error handling and fallback logic

AFTER (OAuth 2.0 Resource Server):
- JWT contains ALL necessary claims (user_id, org_id, permissions)
- Tokens validated locally using JWKS public keys
- No HTTP calls to auth-api for authorization
- No caching needed (permissions are in the token)
- Much simpler, faster, and more resilient

Token Validation Flow:
---------------------
1. JWTAuthMiddleware extracts Bearer token from Authorization header
2. Gets Key ID (kid) from token header
3. Fetches public key from auth-api's JWKS endpoint (cached)
4. Validates token signature, expiry, issuer, audience
5. Stores validated payload in request.state

Authorization Flow:
------------------
1. get_auth_context() dependency reads validated payload from request.state
2. require_permission() dependency checks if permission exists in token's permissions list
3. No remote calls, no caching, purely stateless

JWT Payload Structure (from auth-api):
-------------------------------------
{
    "iss": "http://auth-api:8000",          # Issuer
    "aud": "image-api",                     # Audience
    "sub": "user-uuid",                     # User ID
    "org_id": "org-uuid",                   # Organization ID
    "permissions": [                        # All granted permissions
        "image:upload",
        "image:read",
        "image:delete"
    ],
    "email": "user@example.com",            # Optional
    "name": "John Doe",                     # Optional
    "exp": 1234567890,                      # Expiration timestamp
    "iat": 1234567890                       # Issued at timestamp
}

Usage in Endpoints:
------------------
from app.api.dependencies import require_permission, AuthContext

@router.post("/upload")
async def upload_image(
    file: UploadFile,
    auth: AuthContext = Depends(require_permission("image:upload"))
):
    # User is authenticated AND authorized
    logger.info("upload", user_id=auth.user_id, org_id=auth.org_id)
    # Process upload...

Benefits:
--------
1. Performance: No remote HTTP calls per request
2. Resilience: Can validate tokens even if auth-api is temporarily down
3. Simplicity: No complex caching, circuit breakers, or error handling
4. Security: Standard OAuth 2.0 pattern with RS256 asymmetric keys
5. Scalability: Stateless authorization scales horizontally

Configuration:
-------------
Environment variables in .env:
- AUTH_API_ISSUER_URL: Auth-API issuer URL (e.g., http://auth-api:8000)
- AUTH_API_JWKS_URL: JWKS endpoint URL (e.g., http://auth-api:8000/.well-known/jwks.json)
- AUTH_API_AUDIENCE: Expected audience claim (e.g., "image-api")
- JWT_ALGORITHM: RS256 (asymmetric key validation)
- JWKS_CACHE_TTL: How often to refresh JWKS keys (default: 3600 seconds)

Migration Notes:
---------------
Old symmetric JWT_SECRET_KEY is kept for backward compatibility in testing only.
Production deployments should use the new OAuth 2.0 flow with RS256 tokens
issued by the auth-api.

All authorization logic has been removed:
- AuthorizationService - DELETED (no longer needed)
- AuthorizationCache - DELETED (permissions in token)
- CircuitBreaker - DELETED (no remote calls)
- AuthAPIClient - DELETED (no remote calls)

See:
- app/api/middleware.py: JWTAuthMiddleware, JWKSManager
- app/api/dependencies.py: get_auth_context, require_permission, AuthContext
"""

# This module no longer exports any classes or functions.
# All authorization logic is now in:
# - app/api/middleware.py (JWT validation)
# - app/api/dependencies.py (authorization checks)

# Legacy exports for backward compatibility during migration
# These will be removed in a future version
from app.api.dependencies import AuthContext

__all__ = ["AuthContext"]
