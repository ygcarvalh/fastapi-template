import base64
import binascii
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Annotated, Any, Protocol

from pydantic import BaseModel, Field

DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100

CURSOR_REGEX = r"^[A-Za-z0-9_=-]{1,200}$"
CURSOR_SEPARATOR = "|"


# The cursor is the ordering key, not an index into the result: the row a reader
# is looking at cannot shift because rows arrived above it.
def encode_cursor(created_at: datetime, entry_id: int) -> str:
    raw = f"{created_at.isoformat()}{CURSOR_SEPARATOR}{entry_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(value: str) -> tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(value.encode()).decode()
        moment, entry_id = raw.rsplit(CURSOR_SEPARATOR, 1)
        return datetime.fromisoformat(moment), int(entry_id)
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise ValueError("cursor is not one this API issued") from error


class Identified(Protocol):
    id: int


# The extra row the repository fetched is the only evidence that a next page
# exists, so it decides the cursor and never reaches the caller.
def cursor_slice[EntryT: Identified](
    found: Sequence[EntryT], limit: int, moment: Callable[[EntryT], datetime]
) -> tuple[Sequence[EntryT], str | None]:
    page = list(found[:limit])
    if len(found) <= limit or not page:
        return page, None
    return page, encode_cursor(moment(page[-1]), page[-1].id)


class PageParams(BaseModel):
    limit: Annotated[int, Field(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT
    offset: Annotated[int, Field(ge=0)] = 0


class Page[ItemT](BaseModel):
    items: list[ItemT]
    total: int
    limit: int
    offset: int

    @classmethod
    def of(
        cls,
        rows: Sequence[Any],
        mapper: Callable[[Any], ItemT],
        *,
        total: int,
        params: PageParams,
    ) -> "Page[ItemT]":
        return cls(
            items=[mapper(row) for row in rows],
            total=total,
            limit=params.limit,
            offset=params.offset,
        )


class CursorPage[ItemT](BaseModel):
    """A page that does not know how many rows exist.

    Counting every match is what makes a growing table expensive to read, so a
    collection that grows without bound hands back a cursor instead of a total.
    """

    items: list[ItemT]
    limit: int
    next_cursor: str | None = None

    @classmethod
    def of(
        cls,
        rows: Sequence[Any],
        mapper: Callable[[Any], ItemT],
        *,
        limit: int,
        next_cursor: str | None,
    ) -> "CursorPage[ItemT]":
        return cls(
            items=[mapper(row) for row in rows],
            limit=limit,
            next_cursor=next_cursor,
        )
