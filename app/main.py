import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.request_recorder import store_request
from app.api.v1.router import api_router
from app.core.audit.middleware import register_audit_context
from app.core.config import get_settings
from app.core.http.body_limit import BodySizeLimitMiddleware
from app.core.http.cors import register_cors
from app.core.http.errors import register_exception_handlers
from app.core.http.headers import register_security_headers
from app.core.http.rate_limit import register_rate_limiting
from app.core.observability.logging import configure_logging
from app.core.observability.metrics import register_metrics
from app.core.observability.request_logging import (
    parse_excluded_paths,
    register_request_logging,
)
from app.db.session import dispose_engine, get_engine
from app.schemas.error import COMMON_ERROR_RESPONSES

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_format=settings.log_format == "json",
        service_name=settings.service_name,
        log_file=settings.log_file,
    )
    app = FastAPI(
        title="FastAPI Template",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    register_exception_handlers(app)
    app.add_middleware(
        BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes
    )
    register_rate_limiting(app)
    register_security_headers(app, hsts_enabled=settings.hsts_enabled)
    register_audit_context(app)
    register_request_logging(
        app,
        excluded_paths=parse_excluded_paths(settings.request_log_excluded_paths),
        recorder=store_request if settings.request_log_persist_enabled else None,
    )
    register_cors(app, origins=settings.cors_origin_list)
    if settings.metrics_enabled:
        register_metrics(app)
    app.include_router(api_router, prefix="/api/v1", responses=COMMON_ERROR_RESPONSES)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness() -> JSONResponse:
        try:
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            logger.warning("Readiness probe failed", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not ready"},
            )
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready"})

    return app


app = create_app()
