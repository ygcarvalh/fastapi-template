from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from app import models as _models  # noqa: F401
from app.core.config import get_settings
from app.core.http.rate_limit import reset_rate_limits
from app.db.base import Base
from app.db.seed import seed_roles
from app.db.session import get_session
from app.main import app


@pytest.fixture(autouse=True)
def fresh_rate_limits() -> None:
    reset_rate_limits()


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine]:
    test_database_url = get_settings().test_database_url
    if test_database_url is None:
        raise RuntimeError(
            "TEST_DATABASE_URL is required to run the suite; copy .env.example to .env"
        )
    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSession(bind=engine) as session:
        await seed_roles(session)
        await session.commit()
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    async def override_get_session() -> AsyncGenerator[AsyncSession]:
        yield db_session
        await db_session.commit()

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def user_factory(
    client: AsyncClient,
) -> Callable[..., Awaitable[dict[str, object]]]:
    async def _create(
        email: str = "user@example.com", password: str = "secret123"
    ) -> dict[str, object]:
        response = await client.post(
            "/api/v1/users", json={"email": email, "password": password}
        )
        assert response.status_code == 201
        created: dict[str, object] = response.json()
        return created

    return _create


@pytest_asyncio.fixture
async def auth_client(
    client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> AsyncClient:
    email, password = "auth@example.com", "secret123"
    await user_factory(email="bootstrap@example.com", password=password)
    await user_factory(email=email, password=password)
    response = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": password}
    )
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
