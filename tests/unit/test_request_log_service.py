from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import NotFoundError
from app.models.request_log import RequestLog
from app.models.user import User, UserRole
from app.schemas.request_log import RequestLogQuery, RequestRecord, outcome_for
from app.services.request_log_service import RequestLogService
from tests.unit.fakes import FakeRequestLogRepository

NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def _entry(
    request_id: str,
    *,
    status_code: int = 200,
    user_id: int | None = None,
    path: str = "/api/v1/items",
) -> RequestLog:
    return RequestLog(
        request_id=request_id,
        method="GET",
        path=path,
        status_code=status_code,
        duration_ms=1.5,
        client_ip="127.0.0.1",
        user_id=user_id,
        created_at=NOW,
    )


def _user(user_id: int, role: UserRole = UserRole.USER) -> User:
    return User(
        id=user_id,
        email=f"user{user_id}@example.com",
        hashed_password="x",
        role=role,
    )


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (200, "success"),
        (399, "success"),
        (400, "warning"),
        (499, "warning"),
        (500, "error"),
        (503, "error"),
    ],
)
def test_outcome_follows_the_status_class(status_code: int, expected: str) -> None:
    assert outcome_for(status_code) == expected


async def test_an_admin_reads_every_row() -> None:
    repo = FakeRequestLogRepository(
        [_entry("a", user_id=1), _entry("b", user_id=2), _entry("c")]
    )

    entries, total = await RequestLogService(repo).list_for(
        _user(1, UserRole.ADMIN), RequestLogQuery()
    )

    assert total == 3
    assert [entry.request_id for entry in entries] == ["a", "b", "c"]


async def test_a_user_reads_only_their_own_rows() -> None:
    repo = FakeRequestLogRepository(
        [_entry("a", user_id=1), _entry("b", user_id=2), _entry("c")]
    )

    entries, total = await RequestLogService(repo).list_for(_user(1), RequestLogQuery())

    assert total == 1
    assert [entry.request_id for entry in entries] == ["a"]


async def test_a_user_cannot_ask_for_someone_elses_rows() -> None:
    repo = FakeRequestLogRepository([_entry("a", user_id=1), _entry("b", user_id=2)])

    entries, _ = await RequestLogService(repo).list_for(
        _user(1), RequestLogQuery(user_id=2)
    )

    assert [entry.request_id for entry in entries] == ["a"]


async def test_the_outcome_filter_narrows_the_page() -> None:
    repo = FakeRequestLogRepository(
        [
            _entry("a", user_id=1),
            _entry("b", status_code=404, user_id=1),
            _entry("c", status_code=500, user_id=1),
        ]
    )

    entries, total = await RequestLogService(repo).list_for(
        _user(1), RequestLogQuery(outcome="error")
    )

    assert total == 1
    assert entries[0].status_code == 500


async def test_the_path_filter_matches_a_prefix() -> None:
    repo = FakeRequestLogRepository(
        [
            _entry("items", user_id=1, path="/api/v1/items"),
            _entry("users", user_id=1, path="/api/v1/users/me"),
        ]
    )

    entries, _ = await RequestLogService(repo).list_for(
        _user(1), RequestLogQuery(path="/api/v1/users")
    )

    assert [entry.request_id for entry in entries] == ["users"]


async def test_the_window_filters_by_time() -> None:
    repo = FakeRequestLogRepository([_entry("old", user_id=1)])

    entries, _ = await RequestLogService(repo).list_for(
        _user(1), RequestLogQuery(since=NOW + timedelta(seconds=1))
    )

    assert entries == []


async def test_an_inverted_window_is_refused() -> None:
    with pytest.raises(ValueError, match="since"):
        RequestLogQuery(since=NOW, until=NOW - timedelta(days=1))


async def test_a_page_is_bounded_by_its_limit() -> None:
    repo = FakeRequestLogRepository([_entry(f"row-{i}", user_id=1) for i in range(3)])

    entries, total = await RequestLogService(repo).list_for(
        _user(1), RequestLogQuery(limit=2, offset=1)
    )

    assert total == 3
    assert [entry.request_id for entry in entries] == ["row-1", "row-2"]


async def test_one_row_is_found_by_its_correlation_id() -> None:
    repo = FakeRequestLogRepository([_entry("wanted", user_id=1)])

    entry = await RequestLogService(repo).get_for(_user(1), "wanted")

    assert entry.request_id == "wanted"


async def test_another_users_row_is_not_found() -> None:
    repo = FakeRequestLogRepository([_entry("hidden", user_id=2)])

    with pytest.raises(NotFoundError):
        await RequestLogService(repo).get_for(_user(1), "hidden")


async def test_recording_stores_what_the_middleware_saw() -> None:
    repo = FakeRequestLogRepository()

    entry = await RequestLogService(repo).record(
        RequestRecord(
            request_id="rec-1",
            method="POST",
            path="/api/v1/items",
            status_code=201,
            duration_ms=3.25,
            client_ip="10.0.0.1",
            user_id=7,
        )
    )

    assert (entry.request_id, entry.status_code, entry.user_id) == ("rec-1", 201, 7)


async def test_pruning_removes_a_batch_of_rows_past_the_window() -> None:
    old = [_entry(f"old-{index}", user_id=1) for index in range(3)]
    for entry in old:
        entry.created_at = datetime.now(UTC) - timedelta(days=40)
    repo = FakeRequestLogRepository([*old, _entry("recent", user_id=1)])
    service = RequestLogService(repo)

    first = await service.prune_batch(timedelta(days=30), 2)
    second = await service.prune_batch(timedelta(days=30), 2)

    assert (first, second) == (2, 1)
    assert await repo.count(RequestLogQuery()) == 1
