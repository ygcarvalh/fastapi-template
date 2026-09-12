from fastapi import FastAPI, Request, Response

from app.core.audit.context import AuditContext, set_audit_context
from app.core.http.headers import CallNext
from app.core.observability.request_context import get_request_id


def _context_for(request: Request) -> AuditContext:
    return AuditContext(
        request_id=get_request_id(),
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else None,
    )


def register_audit_context(app: FastAPI) -> None:
    @app.middleware("http")
    async def bind_audit_context(request: Request, call_next: CallNext) -> Response:
        set_audit_context(_context_for(request))
        try:
            return await call_next(request)
        finally:
            set_audit_context(None)
