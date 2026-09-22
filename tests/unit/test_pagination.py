from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.schemas.pagination import (
    CursorPage,
    Page,
    PageParams,
    cursor_slice,
    decode_cursor,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class Entry:
    id: int
    occurred_at: datetime


def entries(count: int) -> list[Entry]:
    return [
        Entry(id=index, occurred_at=START + timedelta(minutes=index))
        for index in range(count)
    ]


def moment(entry: Entry) -> datetime:
    return entry.occurred_at


def test_empty_result_has_no_cursor() -> None:
    empty: list[Entry] = []

    page, cursor = cursor_slice(empty, 20, moment)

    assert page == []
    assert cursor is None


def test_partial_page_has_no_cursor() -> None:
    found = entries(3)

    page, cursor = cursor_slice(found, 20, moment)

    assert page == found
    assert cursor is None


def test_exactly_one_page_has_no_cursor() -> None:
    found = entries(20)

    page, cursor = cursor_slice(found, 20, moment)

    assert len(page) == 20
    assert cursor is None


def test_extra_row_is_dropped_and_becomes_a_cursor() -> None:
    found = entries(21)

    page, cursor = cursor_slice(found, 20, moment)

    assert len(page) == 20
    assert found[20] not in page
    assert cursor is not None
    assert decode_cursor(cursor) == (found[19].occurred_at, found[19].id)


def test_cursor_points_at_the_last_row_kept() -> None:
    found = entries(5)

    page, cursor = cursor_slice(found, 2, moment)

    assert [entry.id for entry in page] == [0, 1]
    assert cursor is not None
    assert decode_cursor(cursor) == (found[1].occurred_at, 1)


def test_page_of_maps_rows_and_carries_params() -> None:
    rows = entries(3)
    params = PageParams(limit=10, offset=5)

    page = Page.of(rows, lambda entry: entry.id, total=42, params=params)

    assert page.items == [0, 1, 2]
    assert page.total == 42
    assert page.limit == 10
    assert page.offset == 5


def test_page_of_with_no_rows_is_still_a_valid_page() -> None:
    page = Page.of([], lambda entry: entry, total=0, params=PageParams())

    assert page.items == []
    assert page.total == 0


def test_cursor_page_of_maps_rows_and_carries_cursor() -> None:
    rows = entries(2)

    page = CursorPage.of(rows, lambda entry: entry.id, limit=20, next_cursor="abc")

    assert page.items == [0, 1]
    assert page.limit == 20
    assert page.next_cursor == "abc"


def test_cursor_page_of_with_no_next_cursor() -> None:
    page = CursorPage.of([], lambda entry: entry, limit=20, next_cursor=None)

    assert page.items == []
    assert page.next_cursor is None
