from datetime import UTC, datetime, timedelta

import pytest

from app.core.audit.policy import AuditAction
from app.core.exceptions import NotFoundError
from app.models.audit_log import AuditLog
from app.models.role import Scope
from app.models.user import User
from app.schemas.audit_log import AuditLogQuery
from app.schemas.pagination import decode_cursor
from app.services.audit_log_service import AuditLogService
from tests.unit.fakes import FakeAuditLogRepository

VIEWER = User(id=1, email="viewer@example.com", hashed_password="x")
SOMEONE_ELSE = 2


def _entry(entry_id: int, actor_id: int, minutes: int = 0) -> AuditLog:
    return AuditLog(
        id=entry_id,
        occurred_at=datetime(2026, 9, 12, 12, tzinfo=UTC) + timedelta(minutes=minutes),
        actor_id=actor_id,
        source="request",
        table_name="items",
        action=AuditAction.INSERT,
        row_pk=str(entry_id),
        changes={},
        truncated=False,
    )


def _service(*entries: AuditLog) -> tuple[AuditLogService, FakeAuditLogRepository]:
    repo = FakeAuditLogRepository(list(entries))
    return AuditLogService(repo), repo


async def test_a_reader_with_the_wider_scope_sees_everyone() -> None:
    service, _ = _service(_entry(1, VIEWER.id), _entry(2, SOMEONE_ELSE, 1))

    entries, _cursor = await service.list_for(VIEWER, Scope.ALL, AuditLogQuery())

    assert [entry.id for entry in entries] == [2, 1]


async def test_a_narrower_scope_is_applied_instead_of_refused() -> None:
    service, _ = _service(_entry(1, VIEWER.id), _entry(2, SOMEONE_ELSE, 1))

    entries, _cursor = await service.list_for(VIEWER, Scope.OWN, AuditLogQuery())

    assert [entry.id for entry in entries] == [1]


async def test_a_narrow_reader_cannot_widen_the_filter_by_asking() -> None:
    service, _ = _service(_entry(1, VIEWER.id), _entry(2, SOMEONE_ELSE, 1))

    entries, _cursor = await service.list_for(
        VIEWER, Scope.OWN, AuditLogQuery(actor_id=SOMEONE_ELSE)
    )

    assert [entry.id for entry in entries] == [1]


async def test_a_full_page_hands_back_the_key_of_its_last_row() -> None:
    service, _ = _service(*(_entry(index, VIEWER.id, index) for index in range(1, 4)))

    entries, cursor = await service.list_for(VIEWER, Scope.ALL, AuditLogQuery(limit=2))

    assert [entry.id for entry in entries] == [3, 2]
    assert cursor is not None
    assert decode_cursor(cursor) == (entries[-1].occurred_at, 2)


async def test_the_last_page_hands_back_nothing_to_ask_for_next() -> None:
    service, _ = _service(_entry(1, VIEWER.id))

    _entries, cursor = await service.list_for(VIEWER, Scope.ALL, AuditLogQuery())

    assert cursor is None


async def test_one_entry_reads_back_by_its_key() -> None:
    service, _ = _service(_entry(1, VIEWER.id))

    assert (await service.get_for(VIEWER, Scope.ALL, 1)).id == 1


async def test_an_entry_outside_the_readers_scope_is_simply_not_there() -> None:
    service, _ = _service(_entry(1, SOMEONE_ELSE))

    with pytest.raises(NotFoundError):
        await service.get_for(VIEWER, Scope.OWN, 1)


async def test_an_entry_that_never_existed_reads_the_same_way() -> None:
    service, _ = _service()

    with pytest.raises(NotFoundError):
        await service.get_for(VIEWER, Scope.ALL, 99)


async def test_pruning_walks_the_table_in_batches() -> None:
    service, repo = _service(*(_entry(index, VIEWER.id) for index in range(1, 6)))

    first = await service.prune_batch(timedelta(days=0), 2)
    second = await service.prune_batch(timedelta(days=0), 2)

    assert (first, second) == (2, 2)
    assert len(repo.pruned) == 2
