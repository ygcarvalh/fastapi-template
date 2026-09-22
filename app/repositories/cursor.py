from datetime import datetime

from sqlalchemy import ColumnElement, tuple_
from sqlalchemy.orm import InstrumentedAttribute

from app.schemas.pagination import decode_cursor


def cursor_condition(
    moment_col: InstrumentedAttribute[datetime],
    id_col: InstrumentedAttribute[int],
    cursor: str | None,
) -> ColumnElement[bool] | None:
    if cursor is None:
        return None
    moment, entry_id = decode_cursor(cursor)
    return tuple_(moment_col, id_col) < (moment, entry_id)
