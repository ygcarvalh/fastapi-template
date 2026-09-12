from typing import Any

from app.core.audit.context import SYSTEM_SOURCE, AuditContext, current_audit_context
from app.core.audit.diff import Changes
from app.core.audit.policy import AuditAction
from app.models.audit_log import AuditLog

IMPERSONATION = "impersonation"


def audit_event(
    table_name: str,
    action: AuditAction,
    row_pk: str | None = None,
    changes: Changes | None = None,
) -> AuditLog:
    context = current_audit_context() or AuditContext(source=SYSTEM_SOURCE)
    recorded: dict[str, Any] = dict(changes or {})
    return AuditLog(
        request_id=context.request_id,
        actor_id=context.actor_id,
        impersonator_id=context.impersonator_id,
        source=context.source,
        method=context.method,
        path=context.path,
        client_ip=context.client_ip,
        table_name=table_name,
        action=action.value,
        row_pk=row_pk,
        changes=recorded,
        truncated=False,
    )
