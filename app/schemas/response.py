"""Common response envelope schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ResponseMeta(BaseModel):
    request_id: str = Field(alias="requestId")
    timestamp: datetime

    model_config = {
        "populate_by_name": True,
    }


class ResponseFeedback(BaseModel):
    code: str
    level: str
    message: str


class ResponseError(BaseModel):
    code: str
    message: str
    details: Optional[dict] = None
    hint: Optional[str] = None


class ResponseEnvelope(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    error: Optional[ResponseError] = None
    meta: ResponseMeta
    feedback: list[ResponseFeedback] = Field(default_factory=list)

    model_config = {
        "populate_by_name": True,
    }
