from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.observability import parse_excluded_paths, register_request_logging
from app.core.request_context import REQUEST_ID_HEADER
from app.core.request_recorder import store_request
from app.models.request_log import RequestLog
from app.schemas.request_log import RequestRecord


@pytest_asyncio.fixture
async def recorded(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        "app.core.request_recorder.get_session_factory", lambda: factory
    )
    yield factory
    async with factory() as session:
        for entry in (await session.execute(select(RequestLog))).scalars().all():
            await session.delete(entry)
        await session.commit()


def _app(recorder: object) -> FastAPI:
    app = FastAPI()
    register_request_logging(
        app,
        excluded_paths=parse_excluded_paths("/health"),
        recorder=recorder,  # type: ignore[arg-type]
    )

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("the real cause")

    return app


async def _get(app: FastAPI, path: str) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get(path, headers={REQUEST_ID_HEADER: "persisted-001"})


async def test_a_served_request_is_recorded() -> None:
    seen: list[RequestRecord] = []

    async def recorder(record: RequestRecord) -> None:
        seen.append(record)

    await _get(_app(recorder), "/ok")

    (record,) = seen
    assert (record.request_id, record.path, record.status_code) == (
        "persisted-001",
        "/ok",
        200,
    )


async def test_excluded_paths_are_not_recorded() -> None:
    seen: list[RequestRecord] = []

    async def recorder(record: RequestRecord) -> None:
        seen.append(record)

    await _get(_app(recorder), "/health")

    assert seen == []


async def test_a_crash_is_recorded_as_a_server_error() -> None:
    seen: list[RequestRecord] = []

    async def recorder(record: RequestRecord) -> None:
        seen.append(record)

    await _get(_app(recorder), "/boom")

    (record,) = seen
    assert record.status_code == 500


async def test_a_failed_write_does_not_break_the_response() -> None:
    async def recorder(record: RequestRecord) -> None:
        raise RuntimeError("the audit table is gone")

    transport = ASGITransport(app=_app(recorder))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ok")

    assert response.status_code == 200


async def test_nothing_is_recorded_without_a_recorder() -> None:
    transport = ASGITransport(app=_app(None))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ok")

    assert response.status_code == 200


async def test_the_default_recorder_writes_a_row(
    recorded: async_sessionmaker[AsyncSession],
) -> None:
    await store_request(
        RequestRecord(
            request_id="stored-001",
            method="GET",
            path="/api/v1/items",
            status_code=200,
            duration_ms=2.5,
            client_ip="127.0.0.1",
        )
    )

    async with recorded() as session:
        stored = (
            (
                await session.execute(
                    select(RequestLog).where(RequestLog.request_id == "stored-001")
                )
            )
            .scalars()
            .one()
        )

    assert stored.path == "/api/v1/items"
    assert stored.created_at is not None
