import pytest

from fastapi import FastAPI, Body, Query
from httpx import ASGITransport, AsyncClient

from app.api.error_handlers import DEFAULT_ERROR_CODE, register_exception_handlers
from app.api.response_middleware import SuccessEnvelopeMiddleware
from app.core.exceptions import KHWException, RecordNotFoundError
from pydantic import BaseModel


@pytest.fixture
def app() -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.add_middleware(SuccessEnvelopeMiddleware)
    register_exception_handlers(fastapi_app)

    @fastapi_app.get("/record")
    async def record_endpoint():
        raise RecordNotFoundError("manual not found")

    @fastapi_app.get("/custom")
    async def custom_endpoint():
        raise KHWException("force fallback")

    @fastapi_app.get("/success")
    async def success_endpoint():
        return {"ok": True}

    @fastapi_app.get("/query-validation")
    async def query_validation_endpoint(q: str = Query(..., min_length=1)):
        return {"q": q}

    class Item(BaseModel):
        name: str

    @fastapi_app.post("/body-validation")
    async def body_validation_endpoint(item: Item):
        return item

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


@pytest.mark.asyncio
async def test_success_response_envelope(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/success")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"ok": True}
    assert body["error"] is None
    assert body["feedback"] == []


@pytest.mark.asyncio
async def test_query_validation_error_envelope(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/query-validation", params={"q": ""})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "ValidationError"
    assert "String should have at least" in body["error"]["message"]
    assert body["feedback"] == []
    assert "meta" in body
    assert body["error"].get("details")


@pytest.mark.asyncio
async def test_body_validation_error_envelope(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/body-validation", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "ValidationError"
    assert "Field required" in body["error"]["message"]
    assert body["feedback"] == []
    assert "meta" in body
    assert body["error"].get("details")
