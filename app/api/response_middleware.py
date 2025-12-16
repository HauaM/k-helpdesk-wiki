"""Middleware to ensure successful responses use the shared envelope."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.response_utils import build_meta
from app.schemas.response import ResponseEnvelope


class SuccessEnvelopeMiddleware(BaseHTTPMiddleware):
    """Wrap successful JSON responses in the shared response envelope."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        if not self._should_wrap(response):
            return response

        body_bytes = await self._extract_body(response)
        if not body_bytes:
            return response

        try:
            payload = json.loads(body_bytes)
        except ValueError:
            return response

        if isinstance(payload, dict) and "success" in payload:
            return response

        envelope = ResponseEnvelope(
            success=True,
            data=payload,
            error=None,
            meta=build_meta(request),
        )

        headers = dict(response.headers)
        return JSONResponse(
            status_code=response.status_code,
            content=jsonable_encoder(envelope, by_alias=True),
            headers=headers,
        )

    async def _extract_body(self, response: Response) -> bytes | None:
        body = getattr(response, "body", None)
        if body:
            return body

        body_iterator = getattr(response, "body_iterator", None)
        if body_iterator is None:
            return None

        data: list[bytes] = []
        async for chunk in body_iterator:
            data.append(chunk)

        return b"".join(data)

    def _should_wrap(self, response: Response) -> bool:
        if response.status_code >= 400:
            return False
        if response.status_code in (204, 304):
            return False

        content_type = response.headers.get("content-type", "")
        return "application/json" in content_type
