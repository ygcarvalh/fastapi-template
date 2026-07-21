from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.exceptions import register_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="FastAPI Template")
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
