from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.rate_limit import (
    RATE_LIMIT_DETAIL,
    RATE_LIMIT_MESSAGE,
    reset_rate_limits,
)
from app.db.session import get_session
from app.main import create_app

LOGIN_ATTEMPTS = 4


@pytest_asyncio.fixture
async def throttled_client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[AsyncClient]:
    get_settings.cache_clear()
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "3/minute")
    monkeypatch.setenv("REGISTER_RATE_LIMIT", "3/minute")
    app = create_app()
    reset_rate_limits()

    async def override_get_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


async def _attempt_login(client: AsyncClient) -> int:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "nobody@example.com", "password": "wrong-password"},
    )
    return response.status_code


async def test_repeated_login_attempts_are_throttled(
    throttled_client: AsyncClient,
) -> None:
    statuses = [await _attempt_login(throttled_client) for _ in range(LOGIN_ATTEMPTS)]

    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429


async def test_repeated_registrations_are_throttled(
    throttled_client: AsyncClient,
) -> None:
    statuses = []
    for index in range(4):
        response = await throttled_client.post(
            "/api/v1/users",
            json={"email": f"flood{index}@example.com", "password": "secret123"},
        )
        statuses.append(response.status_code)

    assert statuses[3] == 429


def test_rate_limit_settings_are_configurable() -> None:
    assert get_settings().login_rate_limit
    assert get_settings().register_rate_limit


async def test_a_throttled_response_carries_the_envelope(
    throttled_client: AsyncClient,
) -> None:
    for _ in range(LOGIN_ATTEMPTS):
        response = await throttled_client.post(
            "/api/v1/auth/login",
            data={"username": "nobody@example.com", "password": "wrong-password"},
        )

    assert response.status_code == 429
    body = response.json()
    assert body["detail"] == RATE_LIMIT_DETAIL
    assert body["message"] == RATE_LIMIT_MESSAGE
    assert body["request_id"] == response.headers["x-request-id"]
