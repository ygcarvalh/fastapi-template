from typing import Annotated

from fastapi import Query

from app.api.deps import AuditLogServiceDep, CurrentUser, require_permission
from app.api.v1.routing import protected_router
from app.core.authorization import AUDIT_LOG, READ
from app.core.features import Feature
from app.models.role import Scope
from app.schemas.audit_log import AuditLogQuery, AuditLogRead
from app.schemas.pagination import CursorPage

private_router = protected_router(
    prefix="/audit", tags=["audit"], feature=Feature.AUDIT_LOG
)


@private_router.get("")
async def list_audit_entries(
    current_user: CurrentUser,
    service: AuditLogServiceDep,
    query: Annotated[AuditLogQuery, Query()],
    scope: Annotated[Scope, require_permission(AUDIT_LOG, READ)],
) -> CursorPage[AuditLogRead]:
    entries, next_cursor = await service.list_for(current_user, scope, query)
    return CursorPage.of(
        entries,
        AuditLogRead.model_validate,
        limit=query.limit,
        next_cursor=next_cursor,
    )


@private_router.get("/{entry_id}")
async def get_audit_entry(
    entry_id: int,
    current_user: CurrentUser,
    service: AuditLogServiceDep,
    scope: Annotated[Scope, require_permission(AUDIT_LOG, READ)],
) -> AuditLogRead:
    entry = await service.get_for(current_user, scope, entry_id)
    return AuditLogRead.model_validate(entry)
