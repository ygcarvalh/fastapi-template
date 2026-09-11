from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app, create_app

ALLOWED = "https://app.example.com"
OTHER = "https://evil.example.com"


@pytest_asyncio.fixture
async def cors_client(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient]:
    get_settings.cache_clear()
    monkeypatch.setenv("CORS_ORIGINS", f"{ALLOWED}, https://staging.example.com")
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    get_settings.cache_clear()


async def test_cors_is_off_by_default() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": ALLOWED})

    assert "access-control-allow-origin" not in response.headers


async def test_a_named_origin_is_allowed_and_sees_the_request_id(
    cors_client: AsyncClient,
) -> None:
    response = await cors_client.get("/health", headers={"Origin": ALLOWED})

    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]


async def test_a_preflight_for_a_named_origin_succeeds(
    cors_client: AsyncClient,
) -> None:
    response = await cors_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, x-request-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED


async def test_an_unnamed_origin_gets_no_cors_headers(
    cors_client: AsyncClient,
) -> None:
    response = await cors_client.get("/health", headers={"Origin": OTHER})

    assert "access-control-allow-origin" not in response.headers


async def test_an_error_response_still_carries_cors_headers(
    cors_client: AsyncClient,
) -> None:
    response = await cors_client.get("/api/v1/users/me", headers={"Origin": ALLOWED})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == ALLOWED
