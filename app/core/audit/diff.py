import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from app.core.audit.policy import (
    MAX_DOCUMENT_BYTES,
    MAX_VALUE_CHARS,
    REDACTED_PLACEHOLDER,
    AuditAction,
    is_ignored,
    is_redacted,
)

Changes = dict[str, dict[str, Any]]

DELETED_AT = "deleted_at"

PASSTHROUGH = (bool, int, float)


def _truncated(length: int) -> dict[str, Any]:
    return {"truncated": True, "length": length}


def jsonable(value: object) -> Any:
    if value is None or isinstance(value, PASSTHROUGH):
        return value
    if isinstance(value, bytes):
        return _truncated(len(value))
    if isinstance(value, Enum):
        return jsonable(value.value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal | UUID):
        return str(value)
    text = value if isinstance(value, str) else str(value)
    if len(text) > MAX_VALUE_CHARS:
        return _truncated(len(text))
    return text


def _rendered(column: str, value: object) -> Any:
    return REDACTED_PLACEHOLDER if is_redacted(column) else jsonable(value)


def changes_from(before: dict[str, Any], after: dict[str, Any]) -> Changes:
    columns = sorted(set(before) | set(after))
    return {
        column: {
            "old": _rendered(column, before.get(column)),
            "new": _rendered(column, after.get(column)),
        }
        for column in columns
        if not is_ignored(column)
    }


def action_for(before: dict[str, Any], after: dict[str, Any]) -> AuditAction:
    if DELETED_AT not in after:
        return AuditAction.UPDATE
    was_deleted = before.get(DELETED_AT) is not None
    is_deleted = after[DELETED_AT] is not None
    if is_deleted and not was_deleted:
        return AuditAction.SOFT_DELETE
    if was_deleted and not is_deleted:
        return AuditAction.RESTORE
    return AuditAction.UPDATE


def cap(changes: Changes) -> tuple[Changes, bool]:
    if len(json.dumps(changes).encode()) <= MAX_DOCUMENT_BYTES:
        return changes, False
    return {"_summary": {"fields": sorted(changes)}}, True
