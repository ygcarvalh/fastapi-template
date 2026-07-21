from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import NotFoundError, register_exception_handlers


async def test_domain_error_maps_to_status() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise NotFoundError("nope")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")
    assert response.status_code == 404
    assert response.json() == {"detail": "nope"}
