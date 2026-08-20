import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app


async def test_metrics_are_served_in_the_prometheus_text_format(
    client: AsyncClient,
) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")


async def test_metrics_count_the_requests_that_came_before(
    client: AsyncClient,
) -> None:
    await client.get("/health")

    body = (await client.get("/metrics")).text

    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body


async def test_metrics_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("METRICS_ENABLED", "false")
    try:
        quiet = create_app()
        transport = ASGITransport(app=quiet)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/metrics")).status_code == 404
    finally:
        get_settings.cache_clear()
