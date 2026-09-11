from collections.abc import AsyncGenerator, AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.body_limit import BODY_TOO_LARGE_DETAIL
from app.core.config import get_settings
from app.main import create_app

LIMIT = 64


@pytest_asyncio.fixture
async def bounded_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[AsyncClient]:
    get_settings.cache_clear()
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", str(LIMIT))
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    get_settings.cache_clear()


async def _chunks(total: int, size: int) -> AsyncIterator[bytes]:
    sent = 0
    while sent < total:
        yield b"x" * size
        sent += size


async def test_an_oversized_body_is_refused_with_the_envelope(
    bounded_client: AsyncClient,
) -> None:
    response = await bounded_client.post(
        "/api/v1/auth/logout", content=b"x" * (LIMIT + 1)
    )

    assert response.status_code == 413
    body = response.json()
    assert body["detail"] == BODY_TOO_LARGE_DETAIL
    assert body["message"] == BODY_TOO_LARGE_DETAIL
    assert body["request_id"] == response.headers["x-request-id"]


async def test_a_chunked_body_is_cut_off_once_it_passes_the_limit(
    bounded_client: AsyncClient,
) -> None:
    response = await bounded_client.post(
        "/api/v1/auth/logout",
        content=_chunks(total=LIMIT * 4, size=16),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


async def test_a_body_at_the_limit_reaches_the_route(
    bounded_client: AsyncClient,
) -> None:
    payload = b'{"refresh_token": "' + b"a" * (LIMIT - 21) + b'"}'
    assert len(payload) == LIMIT

    response = await bounded_client.post(
        "/api/v1/auth/logout",
        content=payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 204


async def test_requests_without_a_body_are_untouched(
    bounded_client: AsyncClient,
) -> None:
    response = await bounded_client.get("/health")

    assert response.status_code == 200


def test_the_default_limit_is_one_mebibyte() -> None:
    assert get_settings().max_request_body_bytes == 1024 * 1024
