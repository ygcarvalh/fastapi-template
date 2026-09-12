from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import ColumnElement, Table, event, inspect
from sqlalchemy.orm import InstanceState, ORMExecuteState, Session, attributes
from sqlalchemy.orm.base import PassiveFlag

from app.core.audit.context import (
    SYSTEM_SOURCE,
    AuditContext,
    current_audit_context,
    is_suppressed,
)
from app.core.audit.diff import Changes, action_for, cap, changes_from
from app.core.audit.policy import AuditAction, is_audited, is_ignored
from app.models.audit_log import AuditLog

PENDING_KEY = "audit_pending"
PK_SEPARATOR = ":"
LABEL_COLUMN = "name"

_registered = False


class UnauditedBulkMutation(RuntimeError):
    def __init__(self, table: str) -> None:
        super().__init__(
            f"A bulk statement against {table} would change rows the audit trail "
            "never sees. Load the rows and change them through the session, or "
            "run inside audit_suppressed()."
        )


AUDIT_TABLE = cast(Table, AuditLog.__table__)


def _state(obj: object) -> InstanceState[Any]:
    return cast(InstanceState[Any], inspect(obj))


@dataclass
class PendingRow:
    obj: object
    table: str
    action: AuditAction
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    row_pk: str | None = None


@dataclass
class PendingLink:
    table: str
    action: AuditAction
    parent: object
    child: object
    parent_column: str
    child_column: str


Pending = PendingRow | PendingLink


def _identity_of(obj: object) -> str | None:
    identity = _state(obj).identity
    if identity is None:
        return None
    return PK_SEPARATOR.join(str(part) for part in identity)


def _loaded_columns(obj: object) -> dict[str, Any]:
    state = _state(obj)
    loaded = state.dict
    return {
        attribute.key: loaded[attribute.key]
        for attribute in state.mapper.column_attrs
        if attribute.key in loaded and not is_ignored(attribute.key)
    }


def _column_history(obj: object) -> tuple[dict[str, Any], dict[str, Any]]:
    state = _state(obj)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for attribute in state.mapper.column_attrs:
        if is_ignored(attribute.key):
            continue
        history = attributes.get_history(
            obj, attribute.key, PassiveFlag.PASSIVE_NO_INITIALIZE
        )
        if not history.has_changes():
            continue
        before[attribute.key] = history.deleted[0] if history.deleted else None
        after[attribute.key] = history.added[0] if history.added else None
    return before, after


def _secondary_column(
    pairs: Sequence[tuple[ColumnElement[Any], ColumnElement[Any]]] | None,
) -> str | None:
    if not pairs:
        return None
    return pairs[0][1].key


def _links(obj: object) -> list[PendingLink]:
    state = _state(obj)
    found: list[PendingLink] = []
    for relationship in state.mapper.relationships:
        secondary = relationship.secondary
        if not isinstance(secondary, Table) or not is_audited(secondary.name):
            continue
        parent_column = _secondary_column(relationship.synchronize_pairs)
        child_column = _secondary_column(relationship.secondary_synchronize_pairs)
        if parent_column is None or child_column is None:
            continue
        history = attributes.get_history(
            obj, relationship.key, PassiveFlag.PASSIVE_NO_INITIALIZE
        )
        if not history.has_changes():
            continue
        for child, action in (
            *((row, AuditAction.LINK) for row in history.added),
            *((row, AuditAction.UNLINK) for row in history.deleted),
        ):
            found.append(
                PendingLink(
                    table=secondary.name,
                    action=action,
                    parent=obj,
                    child=child,
                    parent_column=parent_column,
                    child_column=child_column,
                )
            )
    return found


def _table_of(obj: object) -> str | None:
    table = _state(obj).mapper.local_table
    return table.name if isinstance(table, Table) else None


def _pending_for(session: Session) -> list[Pending]:
    buffered: list[Pending] = session.info.setdefault(PENDING_KEY, [])
    return buffered


def _collect(session: Session) -> None:
    pending = _pending_for(session)
    for obj in session.new:
        table = _table_of(obj)
        if table is not None and is_audited(table):
            pending.append(PendingRow(obj=obj, table=table, action=AuditAction.INSERT))
        pending.extend(_links(obj))
    for obj in session.dirty:
        table = _table_of(obj)
        if table is not None and is_audited(table):
            before, after = _column_history(obj)
            if after:
                pending.append(
                    PendingRow(
                        obj=obj,
                        table=table,
                        action=action_for(before, after),
                        before=before,
                        after=after,
                        row_pk=_identity_of(obj),
                    )
                )
        pending.extend(_links(obj))
    for obj in session.deleted:
        table = _table_of(obj)
        if table is None or not is_audited(table):
            continue
        pending.append(
            PendingRow(
                obj=obj,
                table=table,
                action=AuditAction.DELETE,
                before=_loaded_columns(obj),
                row_pk=_identity_of(obj),
            )
        )


def _label_of(obj: object) -> str | None:
    label = _state(obj).dict.get(LABEL_COLUMN)
    return None if label is None else str(label)


def _link_changes(entry: PendingLink) -> Changes:
    parent_pk = _identity_of(entry.parent)
    child_pk = _identity_of(entry.child)
    changes: Changes = {
        entry.parent_column: {"old": None, "new": parent_pk},
        entry.child_column: {"old": None, "new": child_pk},
    }
    label = _label_of(entry.child)
    if label is not None:
        changes[LABEL_COLUMN] = {"old": None, "new": label}
    if entry.action is not AuditAction.UNLINK:
        return changes
    return {key: {"old": sides["new"], "new": None} for key, sides in changes.items()}


def _row_pk_for(entry: PendingLink) -> str:
    return PK_SEPARATOR.join(
        str(_identity_of(obj)) for obj in (entry.parent, entry.child)
    )


def _resolved(entry: Pending) -> tuple[Changes, str | None] | None:
    if isinstance(entry, PendingLink):
        return _link_changes(entry), _row_pk_for(entry)
    if entry.action is AuditAction.INSERT:
        entry.after = _loaded_columns(entry.obj)
        entry.row_pk = _identity_of(entry.obj)
    changes = changes_from(entry.before, entry.after)
    return (changes, entry.row_pk) if changes else None


def _record(
    context: AuditContext,
    entry: Pending,
    changes: Changes,
    row_pk: str | None,
) -> dict[str, Any]:
    capped, truncated = cap(changes)
    return {
        "request_id": context.request_id,
        "actor_id": context.actor_id,
        "impersonator_id": context.impersonator_id,
        "source": context.source,
        "method": context.method,
        "path": context.path,
        "client_ip": context.client_ip,
        "table_name": entry.table,
        "action": entry.action.value,
        "row_pk": row_pk,
        "changes": capped,
        "truncated": truncated,
    }


def _write(session: Session) -> None:
    pending: list[Pending] = session.info.pop(PENDING_KEY, [])
    if not pending:
        return
    context = current_audit_context() or AuditContext(source=SYSTEM_SOURCE)
    rows: list[dict[str, Any]] = []
    for entry in pending:
        resolved = _resolved(entry)
        if resolved is None:
            continue
        changes, row_pk = resolved
        rows.append(_record(context, entry, changes, row_pk))
    if rows:
        session.connection().execute(AUDIT_TABLE.insert(), rows)


def _discard(session: Session) -> None:
    session.info.pop(PENDING_KEY, None)


def register_audit_listeners(session_class: type[Session] = Session) -> None:
    global _registered
    if _registered:
        return
    _registered = True

    @event.listens_for(session_class, "before_flush")
    def collect(session: Session, flush_context: object, instances: object) -> None:
        if not is_suppressed():
            _collect(session)

    @event.listens_for(session_class, "after_flush_postexec")
    def write(session: Session, flush_context: object) -> None:
        if is_suppressed():
            _discard(session)
            return
        _write(session)

    @event.listens_for(session_class, "do_orm_execute")
    def refuse_silent_bulk(state: ORMExecuteState) -> None:
        if is_suppressed() or not (state.is_update or state.is_delete):
            return
        table = getattr(state.statement, "table", None)
        name = getattr(table, "name", None)
        if isinstance(name, str) and is_audited(name):
            raise UnauditedBulkMutation(name)

    @event.listens_for(session_class, "after_soft_rollback")
    def discard(session: Session, previous_transaction: object) -> None:
        _discard(session)
