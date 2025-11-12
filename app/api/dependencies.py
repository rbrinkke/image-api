"""FastAPI dependencies for authentication, validation, and rate limiting."""

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import magic
from typing import Optional, Callable

from app.core.config import settings
from app.core.authorization import (
    AuthContext,
    get_authorization_service,
    AuthorizationService
)
from app.core.logging_config import get_logger
from app.db.sqlite import get_db


security = HTTPBearer()
logger = get_logger(__name__)


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


async def get_user_id_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """Extract and validate user ID from JWT token.

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        str: User ID from token payload

    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject"
            )
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


async def check_rate_limit(user_id: str = Depends(get_user_id_from_token)) -> dict:
    """Check and enforce upload rate limit for user.

    Args:
        user_id: User identifier from JWT

    Returns:
        dict: Rate limit info with user_id, remaining, reset_at

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    db = get_db()
    result = await db.check_rate_limit(user_id, settings.RATE_LIMIT_MAX_UPLOADS)

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
        "user_id": user_id,
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
# Authorization Dependencies (New)
# ============================================================================


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AuthContext:
    """Extract and validate user context from JWT token.

    Extracts minimal claims: user_id (sub), org_id, email, name.
    Does NOT extract groups/permissions - authorization happens via auth-api + cache.

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        AuthContext: User context with user_id, org_id, email, name

    Raises:
        HTTPException: 401 if token is invalid, expired, or missing required claims
    """
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        user_id = payload.get("sub")
        org_id = payload.get("org_id")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user_id (sub)"
            )

        # BACKWARDS COMPATIBILITY: If org_id not in token, use default
        # This allows old tokens to still work during migration
        if not org_id:
            org_id = "default-org"
            logger.warning(
                "jwt_missing_org_id",
                user_id=user_id,
                message="Token missing org_id - using default. Update JWT issuer to include org_id."
            )

        return AuthContext(
            user_id=user_id,
            org_id=org_id,
            email=payload.get("email"),
            name=payload.get("name")
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except jwt.InvalidTokenError as e:
        logger.warning("jwt_validation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


def require_permission(
    permission: str,
    custom_cache_ttl: Optional[int] = None
) -> Callable:
    """Dependency factory for permission-based authorization.

    Creates a FastAPI dependency that checks if authenticated user has
    the required permission via auth-api (with Redis caching).

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
        custom_cache_ttl: Override default cache TTL for this permission (optional)

    Returns:
        Callable: FastAPI dependency function
    """
    async def _check_permission(
        auth_context: AuthContext = Depends(get_auth_context),
        auth_service: AuthorizationService = Depends(get_authorization_service)
    ) -> AuthContext:
        """Check if user has required permission.

        Args:
            auth_context: Authenticated user context
            auth_service: Authorization service

        Returns:
            AuthContext: User context (if authorized)

        Raises:
            HTTPException: 403 if permission denied, 503 if auth unavailable
        """
        try:
            await auth_service.check_permission(
                auth_context.org_id,
                auth_context.user_id,
                permission,
                custom_cache_ttl
            )

            # Permission granted
            return auth_context

        except Exception as e:
            error_msg = str(e)

            # Determine appropriate HTTP status code
            if "unavailable" in error_msg.lower():
                status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            else:
                status_code = status.HTTP_403_FORBIDDEN

            logger.warning(
                "authorization_failed",
                org_id=auth_context.org_id,
                user_id=auth_context.user_id,
                permission=permission,
                error=error_msg,
                status_code=status_code,
            )

            raise HTTPException(
                status_code=status_code,
                detail=error_msg
            )

    return _check_permission
