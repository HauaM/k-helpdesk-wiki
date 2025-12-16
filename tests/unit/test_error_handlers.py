import pytest

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.error_handlers import DEFAULT_ERROR_CODE, register_exception_handlers
from app.core.exceptions import KHWException, RecordNotFoundError


@pytest.fixture
def app() -> FastAPI:
    fastapi_app = FastAPI()
    register_exception_handlers(fastapi_app)

    @fastapi_app.get("/record")
    async def record_endpoint():
        raise RecordNotFoundError("manual not found")

    @fastapi_app.get("/custom")
    async def custom_endpoint():
        raise KHWException("force fallback")

    return fastapi_app


@pytest.mark.asyncio
async def test_record_not_found_envelope(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/record")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "RecordNotFoundError"
    assert body["error"]["message"] == "manual not found"
    assert body["feedback"] == []
    assert "meta" in body


@pytest.mark.asyncio
async def test_unexpected_error_envelope(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/custom")

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == DEFAULT_ERROR_CODE
    assert body["feedback"] == []
    assert body["data"] is None
