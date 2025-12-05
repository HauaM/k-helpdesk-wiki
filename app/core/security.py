"""
Password hashing utilities
"""

from passlib.context import CryptContext


password_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash plain password using argon2"""
    return password_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against hashed value"""
    return password_context.verify(plain, hashed)
