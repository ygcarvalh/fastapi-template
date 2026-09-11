import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app, create_app


async def test_responses_carry_hardening_headers() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


async def test_hsts_is_absent_by_default() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert "strict-transport-security" not in response.headers


async def test_hsts_is_sent_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("HSTS_ENABLED", "true")
    try:
        hardened = create_app()
        transport = ASGITransport(app=hardened)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
    finally:
        get_settings.cache_clear()

    assert "max-age=" in response.headers["strict-transport-security"]


async def test_docs_are_served_by_default() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/docs")).status_code == 200
        assert (await client.get("/openapi.json")).status_code == 200


async def test_docs_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("DOCS_ENABLED", "false")
    try:
        locked = create_app()
        transport = ASGITransport(app=locked)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/docs")).status_code == 404
            assert (await client.get("/openapi.json")).status_code == 404
            assert (await client.get("/redoc")).status_code == 404
    finally:
        get_settings.cache_clear()
