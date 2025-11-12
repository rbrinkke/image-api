"""FastAPI dependencies for authentication, validation, and rate limiting."""

from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import magic
from typing import Optional, Callable
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.sqlite import get_db


security = HTTPBearer()
logger = get_logger(__name__)


# ============================================================================
# Data Models
# ============================================================================


class AuthContext(BaseModel):
    """Authenticated user context from validated JWT token.

    All data comes from the JWT payload validated by JWTAuthMiddleware.
    No remote API calls needed - this is a pure OAuth 2.0 Resource Server.
    """
    user_id: str
    org_id: str
    permissions: list[str] = []
    email: Optional[str] = None
    name: Optional[str] = None


async def verify_content_length(
    content_length: Optional[int] = Header(None),
    max_size: int = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
):
    """Pre-validate upload size before processing.

    Args:
        content_length: Content-Length header value
        max_size: Maximum allowed file size in bytes

    Raises:
        HTTPException: 413 if file exceeds maximum size

    Returns:
        int: Content length if valid
    """
    if content_length and content_length > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed: {settings.MAX_UPLOAD_SIZE_MB}MB"
        )
    return content_length




def get_auth_context(request: Request) -> AuthContext:
    """Get authenticated user context from JWT payload.

    The JWT has already been validated by JWTAuthMiddleware.
    This dependency just reads the validated payload from request.state.

    Args:
        request: HTTP request with validated JWT payload in state

    Returns:
        AuthContext: User context with permissions

    Raises:
        HTTPException: 401 if not authenticated or invalid token claims
    """
    # Check if user is authenticated (middleware sets this)
    if not hasattr(request.state, "authenticated") or not request.state.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    # Get validated payload from middleware
    if not hasattr(request.state, "auth_payload"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication payload not found"
        )

    payload = request.state.auth_payload

    # Extract required claims
    try:
        return AuthContext(
            user_id=payload["sub"],
            org_id=payload.get("org_id", "default-org"),  # Backward compatibility
            permissions=payload.get("permissions", []),
            email=payload.get("email"),
            name=payload.get("name")
        )
    except (KeyError, ValidationError) as e:
        logger.error(
            "invalid_token_claims",
            error=str(e),
            payload_keys=list(payload.keys()) if payload else []
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token claims: {e}"
        )


async def check_rate_limit(auth: AuthContext = Depends(get_auth_context)) -> dict:
    """Check and enforce upload rate limit for user.

    Args:
        auth: Authenticated user context

    Returns:
        dict: Rate limit info with user_id, remaining, reset_at

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    db = get_db()
    result = await db.check_rate_limit(auth.user_id, settings.RATE_LIMIT_MAX_UPLOADS)

    if not result["allowed"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {settings.RATE_LIMIT_MAX_UPLOADS} uploads per hour.",
            headers={
                "X-RateLimit-Limit": str(settings.RATE_LIMIT_MAX_UPLOADS),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": result["reset_at"],
                "Retry-After": "3600"
            }
        )

    return {
        "user_id": auth.user_id,
        "remaining": result["remaining"],
        "reset_at": result["reset_at"]
    }


async def validate_image_file(file) -> str:
    """Validate uploaded file is an allowed image type using magic bytes.

    Never trust client-provided MIME types - always verify with magic bytes.

    Args:
        file: Uploaded file object

    Returns:
        str: Detected MIME type

    Raises:
        HTTPException: 415 if file type is not allowed
    """
    # Read header for magic byte detection
    header = await file.read(2048)
    mime = magic.from_buffer(header, mime=True)

    # CRITICAL: Rewind file pointer for subsequent reads
    await file.seek(0)

    if mime not in settings.ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {mime}. Allowed: {', '.join(settings.ALLOWED_MIME_TYPES)}"
        )

    return mime


# ============================================================================
# Authorization Dependencies
# ============================================================================


def require_permission(permission: str) -> Callable:
    """Dependency factory for permission-based authorization.

    Checks if the authenticated user has the required permission.
    The permission list comes directly from the validated JWT token.

    No remote API calls - pure OAuth 2.0 Resource Server pattern.

    Usage in endpoint:
        @router.post("/upload")
        async def upload_image(
            file: UploadFile,
            auth: AuthContext = Depends(require_permission("image:upload"))
        ):
            # User is authorized - proceed
            logger.info("upload", user_id=auth.user_id, org_id=auth.org_id)
            ...

    Args:
        permission: Required permission (e.g., "image:upload", "image:read")

    Returns:
        Callable: FastAPI dependency function
    """
    def _check_permission(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        """Check if user has required permission.

        Args:
            auth: Authenticated user context

        Returns:
            AuthContext: User context (if authorized)

        Raises:
            HTTPException: 403 if permission denied
        """
        if permission not in auth.permissions:
            logger.warning(
                "permission_denied",
                user_id=auth.user_id,
                org_id=auth.org_id,
                required_permission=permission,
                user_permissions=auth.permissions,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required"
            )

        # Permission granted
        return auth

    return _check_permission
