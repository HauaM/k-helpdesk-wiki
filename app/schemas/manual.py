"""
Manual Schemas
Pydantic models for Manual API requests/responses
"""

from uuid import UUID
from pydantic import Field

from app.models.manual import ManualStatus
from app.models.task import TaskStatus
from app.schemas.base import BaseSchema, BaseResponseSchema


class ManualEntryBase(BaseSchema):
    """
    Base manual entry fields
    """

    keywords: list[str] = Field(min_length=1, max_length=3)
    topic: str = Field(min_length=5, max_length=200)
    background: str = Field(min_length=10)
    guideline: str = Field(min_length=10)
    business_type: str | None = None
    error_code: str | None = None


class ManualEntryCreate(ManualEntryBase):
    """
    Schema for creating manual entry draft

    RFP Reference: POST /consultations/{id}/manual-draft
    """

    source_consultation_id: UUID


class ManualEntryUpdate(BaseSchema):
    """
    Schema for updating manual entry
    """

    keywords: list[str] | None = None
    topic: str | None = None
    background: str | None = None
    guideline: str | None = None
    status: ManualStatus | None = None


class ManualEntryResponse(ManualEntryBase, BaseResponseSchema):
    """
    Schema for manual entry response
    """

    source_consultation_id: UUID
    version_id: UUID | None
    status: ManualStatus


class ManualSearchParams(BaseSchema):
    """
    Search parameters for manuals

    RFP Reference: GET /manuals/search
    """

    query: str = Field(min_length=1)
    business_type: str | None = None
    error_code: str | None = None
    status: ManualStatus | None = None
    top_k: int = Field(default=10, ge=1, le=50)
    similarity_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class ManualSearchResult(BaseSchema):
    """
    Single manual search result
    """

    manual: ManualEntryResponse
    similarity_score: float


class ManualVersionResponse(BaseResponseSchema):
    """
    Manual version response
    """

    version: str
    description: str | None
    changelog: dict | None


class ManualReviewTaskResponse(BaseResponseSchema):
    """
    Manual review task response

    RFP Reference: GET /tasks/manual-review
    """

    old_entry_id: UUID | None
    new_entry_id: UUID
    similarity: float
    status: TaskStatus
    reviewer_id: UUID | None
    review_notes: str | None

    # TODO: Optionally include full manual entries for comparison
    # old_entry: ManualEntryResponse | None
    # new_entry: ManualEntryResponse


class ManualReviewApproval(BaseSchema):
    """
    Schema for approving manual review

    RFP Reference: POST /tasks/manual-review/{id}/approve
    """

    review_notes: str | None = None
    create_new_version: bool = Field(
        default=True, description="Create new manual version"
    )


class ManualReviewRejection(BaseSchema):
    """
    Schema for rejecting manual review

    RFP Reference: POST /tasks/manual-review/{id}/reject
    """

    review_notes: str = Field(min_length=10, description="Reason for rejection")
