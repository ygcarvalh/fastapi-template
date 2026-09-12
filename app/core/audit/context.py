from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

REQUEST_SOURCE = "request"
SYSTEM_SOURCE = "system"


@dataclass
class AuditContext:
    request_id: str | None = None
    method: str | None = None
    path: str | None = None
    client_ip: str | None = None
    actor_id: int | None = None
    impersonator_id: int | None = None
    source: str = REQUEST_SOURCE


_audit_context: ContextVar[AuditContext | None] = ContextVar(
    "audit_context", default=None
)
_suppressed: ContextVar[bool] = ContextVar("audit_suppressed", default=False)


def current_audit_context() -> AuditContext | None:
    return _audit_context.get()


def set_audit_context(context: AuditContext | None) -> None:
    _audit_context.set(context)


def bind_actor(actor_id: int | None, impersonator_id: int | None = None) -> None:
    context = _audit_context.get()
    if context is None:
        return
    context.actor_id = actor_id
    context.impersonator_id = impersonator_id


def is_suppressed() -> bool:
    return _suppressed.get()


@contextmanager
def audit_suppressed() -> Iterator[None]:
    token = _suppressed.set(True)
    try:
        yield
    finally:
        _suppressed.reset(token)
