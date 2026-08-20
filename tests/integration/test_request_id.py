from httpx import AsyncClient

from app.core.request_context import MAX_REQUEST_ID_LENGTH, REQUEST_ID_HEADER

HEADER = REQUEST_ID_HEADER.lower()


async def test_a_wellformed_inbound_id_is_reused(client: AsyncClient) -> None:
    response = await client.get("/health", headers={REQUEST_ID_HEADER: "abc-123"})

    assert response.headers[HEADER] == "abc-123"


async def test_an_id_is_minted_when_the_caller_sends_none(
    client: AsyncClient,
) -> None:
    response = await client.get("/health")

    assert len(response.headers[HEADER]) == 32


async def test_a_malformed_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get(
        "/health", headers={REQUEST_ID_HEADER: "a" * (MAX_REQUEST_ID_LENGTH + 1)}
    )

    assert len(response.headers[HEADER]) == 32


async def test_every_request_gets_its_own_id(client: AsyncClient) -> None:
    first = await client.get("/health")
    second = await client.get("/health")

    assert first.headers[HEADER] != second.headers[HEADER]


async def test_an_error_response_still_carries_the_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/items/999999")

    assert response.status_code == 401
    assert response.headers[HEADER]
