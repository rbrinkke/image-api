"""FastAPI dependencies for authentication, validation, and rate limiting."""

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import magic
from typing import Optional

from app.core.config import settings
from app.db.sqlite import get_db


security = HTTPBearer()


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
