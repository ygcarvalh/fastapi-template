from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.core.audit.diff import action_for, cap, changes_from, jsonable
from app.core.audit.policy import (
    MAX_DOCUMENT_BYTES,
    MAX_VALUE_CHARS,
    REDACTED_PLACEHOLDER,
    AuditAction,
)
from app.models.role import Scope


def test_a_scalar_the_database_holds_survives_the_trip_to_json() -> None:
    assert jsonable(None) is None
    assert jsonable(True) is True
    assert jsonable(7) == 7
    assert jsonable(1.5) == 1.5
    assert jsonable("plain") == "plain"


def test_a_value_json_cannot_hold_is_rendered_rather_than_dropped() -> None:
    moment = datetime(2026, 9, 12, 14, 30, tzinfo=UTC)

    assert jsonable(moment) == moment.isoformat()
    assert jsonable(Scope.ALL) == "all"
    assert jsonable(Decimal("1.25")) == "1.25"
    assert jsonable(UUID(int=1)) == str(UUID(int=1))


def test_a_long_value_is_measured_rather_than_stored() -> None:
    rendered = jsonable("x" * (MAX_VALUE_CHARS + 1))

    assert rendered == {"truncated": True, "length": MAX_VALUE_CHARS + 1}


def test_a_binary_value_is_never_copied_into_the_trail() -> None:
    assert jsonable(b"\x00\x01\x02") == {"truncated": True, "length": 3}


def test_a_change_carries_both_sides() -> None:
    changes = changes_from({"title": "before"}, {"title": "after"})

    assert changes == {"title": {"old": "before", "new": "after"}}


def test_a_secret_records_that_it_changed_and_never_what_to() -> None:
    changes = changes_from({"hashed_password": "old"}, {"hashed_password": "new"})

    assert changes == {
        "hashed_password": {
            "old": REDACTED_PLACEHOLDER,
            "new": REDACTED_PLACEHOLDER,
        }
    }


def test_the_columns_the_database_writes_by_itself_stay_out() -> None:
    changes = changes_from(
        {"created_at": "then", "updated_at": "then"},
        {"created_at": "then", "updated_at": "now", "title": "after"},
    )

    assert changes == {"title": {"old": None, "new": "after"}}


def test_an_insert_reads_as_a_change_from_nothing() -> None:
    changes = changes_from({}, {"title": "first"})

    assert changes == {"title": {"old": None, "new": "first"}}


def test_a_soft_delete_is_told_apart_from_an_ordinary_update() -> None:
    marked = {"deleted_at": datetime(2026, 9, 12, tzinfo=UTC)}

    assert action_for({"deleted_at": None}, marked) == AuditAction.SOFT_DELETE
    assert action_for(marked, {"deleted_at": None}) == AuditAction.RESTORE
    assert action_for({"title": "a"}, {"title": "b"}) == AuditAction.UPDATE


def test_a_row_that_was_already_deleted_is_not_deleted_twice() -> None:
    marked = {"deleted_at": datetime(2026, 9, 12, tzinfo=UTC)}

    assert action_for(marked, marked) == AuditAction.UPDATE


def test_a_diff_that_fits_is_left_alone() -> None:
    changes = {"title": {"old": "a", "new": "b"}}

    assert cap(changes) == (changes, False)


def test_a_diff_too_large_to_store_keeps_the_field_names() -> None:
    wide = {
        f"column_{index}": {"old": "x" * 900, "new": "y" * 900}
        for index in range(MAX_DOCUMENT_BYTES // 1800 + 2)
    }

    capped, truncated = cap(wide)

    assert truncated
    assert capped == {"_summary": {"fields": sorted(wide)}}
