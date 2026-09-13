from enum import StrEnum
from typing import NamedTuple


class ClaimState(StrEnum):
    FRESH = "fresh"
    REPLAY = "replay"
    MISMATCH = "mismatch"
    IN_FLIGHT = "in-flight"


class StoredResponse(NamedTuple):
    status_code: int
    body: str
    content_type: str | None


class Attempt(NamedTuple):
    user_id: int
    key: str
    method: str
    path: str
    body: bytes


class Claim(NamedTuple):
    state: ClaimState
    stored: StoredResponse | None = None
