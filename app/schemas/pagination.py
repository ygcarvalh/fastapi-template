from typing import Annotated

from pydantic import BaseModel, Field

DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100


class PageParams(BaseModel):
    limit: Annotated[int, Field(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT
    offset: Annotated[int, Field(ge=0)] = 0


class Page[ItemT](BaseModel):
    items: list[ItemT]
    total: int
    limit: int
    offset: int


class CursorPage[ItemT](BaseModel):
    """A page that does not know how many rows exist.

    Counting every match is what makes a growing table expensive to read, so a
    collection that grows without bound hands back a cursor instead of a total.
    """

    items: list[ItemT]
    limit: int
    next_cursor: str | None = None
