from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app


@pytest_asyncio.fixture
async def only_items(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[AsyncClient]:
    get_settings.cache_clear()
    monkeypatch.setenv("FEATURE_FLAGS", "items")
    app = create_app()

    async def override_get_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


async def test_the_enabled_flags_need_a_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/features")

    assert response.status_code == 401


async def test_a_signed_in_caller_reads_the_enabled_flags(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/api/v1/features")

    assert response.status_code == 200
    assert response.json() == {"flags": ["items", "request-log"], "inherited": None}


async def test_a_disabled_feature_is_absent(only_items: AsyncClient) -> None:
    refused = await only_items.get("/api/v1/requests")

    assert refused.status_code == 404
    assert refused.json()["detail"] == "Not Found"
