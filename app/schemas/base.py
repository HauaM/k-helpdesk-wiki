"""
Base Pydantic schemas
"""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """
    Base schema with common configuration
    """

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode (SQLAlchemy compatibility)
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=False,  # Return enum objects, not string values
    )


class TimestampSchema(BaseSchema):
    """
    Schema with timestamp fields
    """

    created_at: datetime
    updated_at: datetime


class IDSchema(BaseSchema):
    """
    Schema with UUID ID
    """

    id: UUID


class BaseResponseSchema(IDSchema, TimestampSchema):
    """
    Base response schema with ID and timestamps
    """

    pass


class PaginationParams(BaseSchema):
    """
    Common pagination parameters
    """

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        """Calculate offset for database query"""
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseSchema):
    """
    Generic paginated response wrapper
    """

    items: list[BaseSchema] = Field(default_factory=list)
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)

    @classmethod
    def create(
        cls,
        items: list[BaseSchema],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse":
        """
        Create paginated response

        Args:
            items: List of items for current page
            total: Total number of items
            page: Current page number
            page_size: Items per page

        Returns:
            PaginatedResponse instance
        """
        total_pages = (total + page_size - 1) // page_size
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
