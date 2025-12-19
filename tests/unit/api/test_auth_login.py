import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.routers import auth
from app.schemas.user import TokenResponse, UserLogin


class DummyLoginService:
    """Minimal service stub that records the last payload."""

    def __init__(self) -> None:
        self.calls: list[UserLogin] = []

    async def login(self, user_login: UserLogin) -> TokenResponse:
        self.calls.append(user_login)
        return TokenResponse(access_token="stub-access-token")


@pytest.fixture
def auth_client(monkeypatch) -> tuple[TestClient, DummyLoginService]:
    """Override the user service and embedding warmup for predictable responses."""

    service = DummyLoginService()
    app.dependency_overrides[auth.get_user_service] = lambda: service

    class NoOpEmbeddingService:
        async def warmup(self) -> None:
            return None

    monkeypatch.setattr(
        "app.api.main.get_embedding_service",
        lambda: NoOpEmbeddingService(),
    )
    with TestClient(app) as client:
        yield client, service
    app.dependency_overrides.pop(auth.get_user_service, None)


def test_login_via_oauth2_form(auth_client: tuple[TestClient, DummyLoginService]) -> None:
    client, service = auth_client

    response = client.post(
        "/api/v1/auth/login",
        data={
            "grant_type": "password",
            "username": "form-user",
            "password": "secret",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["access_token"] == "stub-access-token"
    assert service.calls[-1].username == "form-user"


def test_login_via_json_body(auth_client: tuple[TestClient, DummyLoginService]) -> None:
    client, service = auth_client

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "json-user",
            "password": "json-secret",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["access_token"] == "stub-access-token"
    assert service.calls[-1].username == "json-user"
