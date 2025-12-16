"""Shared helpers for building API response envelopes."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Request

from app.schemas.response import ResponseMeta


def build_meta(request: Request) -> ResponseMeta:
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    return ResponseMeta(requestId=request_id, timestamp=datetime.now(timezone.utc))
