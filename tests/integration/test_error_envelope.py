from collections.abc import AsyncGenerator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.http.errors import UNEXPECTED_DETAIL, UNEXPECTED_MESSAGE
from app.core.observability.request_context import REQUEST_ID_HEADER
from app.db.session import get_session
from app.main import create_app

HEADER = REQUEST_ID_HEADER.lower()
SENT_ID = "envelope-001"


def _app_that_crashes() -> FastAPI:
    crashing = create_app()

    @crashing.get("/boom")
    async def boom() -> None:
        raise RuntimeError("connection string is postgres://u:hunter2@db")

    return crashing


@pytest_asyncio.fixture
async def crashing_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    app = _app_that_crashes()

    async def override_get_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def test_an_unauthenticated_call_explains_itself(client: AsyncClient) -> None:
    response = await client.get("/api/v1/items", headers={REQUEST_ID_HEADER: SENT_ID})

    body = response.json()
    assert response.status_code == 401
    assert body["message"]
    assert body["code"] == ErrorCode.UNAUTHORIZED
    assert body["request_id"] == SENT_ID == response.headers[HEADER]


async def test_a_conflict_explains_itself(
    client: AsyncClient, auth_client: AsyncClient
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={"email": "auth@example.com", "password": "secret123"},
        headers={REQUEST_ID_HEADER: SENT_ID},
    )

    body = response.json()
    assert response.status_code == 409
    assert body["detail"] == body["message"] == "Email already registered"
    assert body["code"] == ErrorCode.USER_EMAIL_TAKEN
    assert body["request_id"] == SENT_ID


async def test_a_missing_row_explains_itself(auth_client: AsyncClient) -> None:
    response = await auth_client.get(
        "/api/v1/items/999999", headers={REQUEST_ID_HEADER: SENT_ID}
    )

    assert response.status_code == 404
    assert response.json()["code"] == ErrorCode.ITEM_NOT_FOUND
    assert response.json()["request_id"] == SENT_ID


async def test_a_crash_carries_the_id_in_the_body_and_the_header(
    crashing_client: AsyncClient,
) -> None:
    response = await crashing_client.get("/boom", headers={REQUEST_ID_HEADER: SENT_ID})

    body = response.json()
    assert response.status_code == 500
    assert body == {
        "detail": UNEXPECTED_DETAIL,
        "message": UNEXPECTED_MESSAGE,
        "code": ErrorCode.UNEXPECTED,
        "params": {},
        "request_id": SENT_ID,
    }
    # Starlette serves this one above the middleware that sets the header, so
    # the handler has to set it itself.
    assert response.headers[HEADER] == SENT_ID
    assert "hunter2" not in response.text


async def test_an_unrouted_path_explains_itself(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/nothing-here", headers={REQUEST_ID_HEADER: SENT_ID}
    )

    body = response.json()
    assert response.status_code == 404
    assert body["message"] == body["detail"] == "Not Found"
    assert body["code"] == ErrorCode.NOT_FOUND
    assert body["request_id"] == SENT_ID


async def test_a_bearer_challenge_survives_the_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/items")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_a_validation_failure_carries_what_a_translation_needs(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/api/v1/items", params={"limit": 500})

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == ErrorCode.VALIDATION
    failure = body["detail"][0]
    assert failure["type"] == "less_than_equal"
    assert failure["loc"] == ["query", "limit"]
    assert failure["ctx"] == {"le": 100}


async def test_validation_context_drops_anything_that_is_not_a_scalar(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/users", json={"email": "not-an-address", "password": "secret123"}
    )

    body = response.json()
    assert response.status_code == 422
    for failure in body["detail"]:
        for value in failure["ctx"].values():
            assert isinstance(value, str | int)
