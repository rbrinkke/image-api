"""JWT authentication helpers for mock servers."""

import jwt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional


def generate_test_jwt(
    user_id: str = "test-user-123",
    secret: str = "dev-secret-change-in-production",
    algorithm: str = "HS256",
    expires_minutes: int = 60,
    extra_claims: Optional[Dict[str, Any]] = None
) -> str:
    """Generate JWT token for testing.

    Creates a valid JWT token matching the format expected by the image API.
    Useful for testing authenticated endpoints without a real auth provider.

    Args:
        user_id: Subject claim (user identifier)
        secret: Secret key for signing (must match API secret)
        algorithm: JWT algorithm (HS256, RS256, etc.)
        expires_minutes: Token expiration time in minutes
        extra_claims: Additional JWT claims to include

    Returns:
        Encoded JWT token string

    Example:
        >>> token = generate_test_jwt(user_id="user-456", expires_minutes=30)
        >>> # Use in Authorization header: f"Bearer {token}"
    """
    payload = {
        "sub": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes)
    }

    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, secret, algorithm=algorithm)


def verify_test_jwt(
    token: str,
    secret: str = "dev-secret-change-in-production",
    algorithm: str = "HS256"
) -> Dict[str, Any]:
    """Verify and decode JWT token.

    Validates token signature and expiration, then returns decoded payload.

    Args:
        token: JWT token string (without "Bearer " prefix)
        secret: Secret key for verification
        algorithm: JWT algorithm

    Returns:
        Decoded JWT payload dictionary

    Raises:
        jwt.InvalidTokenError: If token is invalid or expired
        jwt.ExpiredSignatureError: If token has expired
        jwt.DecodeError: If token cannot be decoded

    Example:
        >>> payload = verify_test_jwt(token)
        >>> user_id = payload["sub"]
    """
    return jwt.decode(token, secret, algorithms=[algorithm])


def extract_user_id(token: str, secret: str = "dev-secret-change-in-production") -> Optional[str]:
    """Extract user ID from JWT token.

    Convenience function to get user_id without handling exceptions.

    Args:
        token: JWT token string
        secret: Secret key

    Returns:
        User ID from "sub" claim, or None if invalid

    Example:
        >>> user_id = extract_user_id(request.headers.get("Authorization", "").replace("Bearer ", ""))
    """
    try:
        payload = verify_test_jwt(token, secret)
        return payload.get("sub")
    except Exception:
        return None
