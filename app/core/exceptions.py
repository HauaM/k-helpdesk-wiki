"""
Custom Exceptions for KHW Application
"""


class KHWException(Exception):
    """Base exception for all KHW errors"""

    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code or self.__class__.__name__
        super().__init__(self.message)


# Database Exceptions
class DatabaseError(KHWException):
    """Database operation failed"""

    pass


class RecordNotFoundError(KHWException):
    """Requested record not found in database"""

    pass


class DuplicateRecordError(KHWException):
    """Attempted to create duplicate record"""

    pass


# VectorStore Exceptions
class VectorStoreError(KHWException):
    """VectorStore operation failed"""

    pass


class VectorIndexError(VectorStoreError):
    """Failed to index vector"""

    pass


class VectorSearchError(VectorStoreError):
    """Failed to search vectors"""

    pass


# LLM Exceptions
class LLMError(KHWException):
    """LLM operation failed"""

    pass


class LLMHallucinationError(LLMError):
    """LLM generated content not present in source"""

    pass


class LLMValidationError(LLMError):
    """LLM output failed validation"""

    pass


class LLMRateLimitError(LLMError):
    """LLM API rate limit exceeded"""

    pass


# Business Logic Exceptions
class BusinessLogicError(KHWException):
    """Business rule violation"""

    pass


class ManualConflictError(BusinessLogicError):
    """Manual entry conflicts with existing manual"""

    pass


class InvalidStatusTransitionError(BusinessLogicError):
    """Invalid status transition attempted"""

    pass


# Queue Exceptions
class QueueError(KHWException):
    """Queue operation failed"""

    pass


class RetryLimitExceededError(QueueError):
    """Maximum retry attempts exceeded"""

    pass


# Validation Exceptions
class ValidationError(KHWException):
    """Input validation failed"""

    pass


class AuthenticationError(KHWException):
    """Authentication failed"""

    pass


class AuthorizationError(KHWException):
    """User not authorized for this operation"""

    pass


class JWTDecodeError(AuthenticationError):
    """JWT decoding failed"""

    pass
