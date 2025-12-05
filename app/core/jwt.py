"""
JWT utility functions
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import JWTDecodeError


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Create JWT access token with expiration

    Args:
        data: Claims to encode
        expires_delta: Optional override for expiration duration
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate JWT access token

    Raises:
        JWTDecodeError: if token is invalid or expired
    """
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise JWTDecodeError("Invalid or expired access token") from exc
