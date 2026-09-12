from typing import Annotated

from fastapi import Depends, Header

from app.core.exceptions import PreconditionFailedError, PreconditionRequiredError

ETAG_HEADER = "ETag"
ANY_VERSION = "*"
WEAK_PREFIX = "W/"

MISSING_IF_MATCH = "This write needs an If-Match header carrying the ETag you last read"
UNREADABLE_IF_MATCH = "If-Match does not carry an ETag this API issued"


def etag_for(version: int) -> str:
    return f'{WEAK_PREFIX}"{version}"'


def parse_etag(value: str) -> int | None:
    candidate = value.strip()
    if candidate.startswith(WEAK_PREFIX):
        candidate = candidate[len(WEAK_PREFIX) :]
    candidate = candidate.strip('"')
    try:
        return int(candidate)
    except ValueError:
        return None


async def require_if_match(
    if_match: Annotated[str | None, Header()] = None,
) -> int | None:
    if if_match is None:
        raise PreconditionRequiredError(MISSING_IF_MATCH)
    if if_match.strip() == ANY_VERSION:
        return None
    version = parse_etag(if_match)
    if version is None:
        raise PreconditionFailedError(UNREADABLE_IF_MATCH)
    return version


IfMatch = Annotated[int | None, Depends(require_if_match)]
