"""Mock Auth-API server for testing authorization system.

This mock server simulates the external auth-api that the image-api
communicates with for permission checks.

Usage:
    python tests/mock_auth_api.py

The mock API will run on http://localhost:8001 and provide:
- POST /api/v1/authorization/check - Permission check endpoint
- GET /health - Health check endpoint
- POST /admin/users - Add test users with permissions
- DELETE /admin/users/{user_id} - Remove test users
"""

from typing import Dict, Set, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn


# Data models
class PermissionCheckRequest(BaseModel):
    """Request model for permission check."""
    user_id: str
    org_id: str
    permission: str


class PermissionCheckResponse(BaseModel):
    """Response model for permission check."""
    allowed: bool
    reason: Optional[str] = None


class UserPermissionsRequest(BaseModel):
    """Request to add user with permissions."""
    user_id: str
    org_id: str
    permissions: list[str]


# Mock data store
class MockAuthStore:
    """In-memory store for mock auth data."""

    def __init__(self):
        # Structure: {org_id: {user_id: set(permissions)}}
        self.permissions: Dict[str, Dict[str, Set[str]]] = {}

        # Pre-populate with test users
        self.add_user("test-org-456", "test-user-123", {
            "image:read",
            "image:upload",
            "image:delete"
        })
        self.add_user("test-org-456", "admin-user-789", {
            "image:read",
            "image:upload",
            "image:delete",
            "image:admin",
            "org:admin"
        })
        self.add_user("test-org-456", "readonly-user-999", {
            "image:read"
        })

        # Different org
        self.add_user("other-org-111", "test-user-123", {
            "image:read"  # Same user, different org, different permissions
        })

    def add_user(self, org_id: str, user_id: str, permissions: Set[str]):
        """Add user with permissions."""
        if org_id not in self.permissions:
            self.permissions[org_id] = {}
        self.permissions[org_id][user_id] = permissions

    def remove_user(self, org_id: str, user_id: str):
        """Remove user."""
        if org_id in self.permissions and user_id in self.permissions[org_id]:
            del self.permissions[org_id][user_id]

    def check_permission(self, org_id: str, user_id: str, permission: str) -> tuple[bool, str]:
        """Check if user has permission.

        Returns:
            (allowed: bool, reason: str)
        """
        # Check org exists
        if org_id not in self.permissions:
            return False, f"Organization not found: {org_id}"

        # Check user exists in org
        if user_id not in self.permissions[org_id]:
            return False, f"User not found in organization: {user_id}"

        # Check permission
        user_permissions = self.permissions[org_id][user_id]

        # Direct permission check
        if permission in user_permissions:
            return True, "Direct permission granted"

        # Check wildcard admin permissions
        if "org:admin" in user_permissions:
            return True, "Granted via org:admin"

        if permission.startswith("image:") and "image:admin" in user_permissions:
            return True, "Granted via image:admin"

        return False, f"Permission denied: user does not have '{permission}'"

    def get_user_permissions(self, org_id: str, user_id: str) -> Optional[Set[str]]:
        """Get all permissions for a user."""
        if org_id in self.permissions and user_id in self.permissions[org_id]:
            return self.permissions[org_id][user_id]
        return None


# Create FastAPI app
app = FastAPI(
    title="Mock Auth API",
    description="Mock authentication/authorization API for testing",
    version="1.0.0"
)

# Create store
store = MockAuthStore()


@app.post("/api/v1/authorization/check", response_model=PermissionCheckResponse)
async def check_permission(request: PermissionCheckRequest):
    """Check if user has permission.

    This is the main endpoint that image-api calls to verify permissions.
    """
    allowed, reason = store.check_permission(
        org_id=request.org_id,
        user_id=request.user_id,
        permission=request.permission
    )

    return PermissionCheckResponse(allowed=allowed, reason=reason)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "mock-auth-api",
        "version": "1.0.0"
    }


@app.post("/admin/users")
async def add_user(request: UserPermissionsRequest):
    """Add user with permissions (test helper)."""
    store.add_user(
        org_id=request.org_id,
        user_id=request.user_id,
        permissions=set(request.permissions)
    )

    return {
        "status": "created",
        "org_id": request.org_id,
        "user_id": request.user_id,
        "permissions": list(request.permissions)
    }


@app.delete("/admin/users/{org_id}/{user_id}")
async def remove_user(org_id: str, user_id: str):
    """Remove user (test helper)."""
    store.remove_user(org_id=org_id, user_id=user_id)

    return {
        "status": "deleted",
        "org_id": org_id,
        "user_id": user_id
    }


@app.get("/admin/users/{org_id}/{user_id}")
async def get_user_permissions(org_id: str, user_id: str):
    """Get user permissions (test helper)."""
    permissions = store.get_user_permissions(org_id=org_id, user_id=user_id)

    if permissions is None:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "org_id": org_id,
        "user_id": user_id,
        "permissions": list(permissions)
    }


@app.get("/admin/debug")
async def debug_info():
    """Debug endpoint to see all users and permissions."""
    result = {}
    for org_id, users in store.permissions.items():
        result[org_id] = {
            user_id: list(perms)
            for user_id, perms in users.items()
        }
    return result


if __name__ == "__main__":
    print("=" * 70)
    print("Mock Auth API Server")
    print("=" * 70)
    print()
    print("Starting server on http://localhost:8001")
    print()
    print("Endpoints:")
    print("  POST   http://localhost:8001/api/v1/authorization/check")
    print("  GET    http://localhost:8001/health")
    print("  POST   http://localhost:8001/admin/users")
    print("  DELETE http://localhost:8001/admin/users/{org_id}/{user_id}")
    print("  GET    http://localhost:8001/admin/users/{org_id}/{user_id}")
    print("  GET    http://localhost:8001/admin/debug")
    print()
    print("Pre-configured test users:")
    print("  - test-user-123 (test-org-456): image:read, image:upload, image:delete")
    print("  - admin-user-789 (test-org-456): all permissions")
    print("  - readonly-user-999 (test-org-456): image:read only")
    print()
    print("=" * 70)
    print()

    uvicorn.run(app, host="0.0.0.0", port=8001)
