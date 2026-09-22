from starlette.types import Receive, Scope, Send

from app.core.observability.request_logging import RequestLoggingMiddleware
from app.schemas.request_log import RequestRecord

RECORD = RequestRecord(
    request_id="r-1", method="GET", path="/x", status_code=200, duration_ms=1.0
)


async def _unreachable_app(scope: Scope, receive: Receive, send: Send) -> None:
    raise AssertionError("the downstream app is never called by this test")


def _middleware(recorder: object) -> RequestLoggingMiddleware:
    return RequestLoggingMiddleware(
        _unreachable_app,
        excluded_paths=[],
        recorder=recorder,  # type: ignore[arg-type]
    )


async def test_a_record_is_handed_to_the_recorder() -> None:
    seen: list[RequestRecord] = []

    async def recorder(record: RequestRecord) -> None:
        seen.append(record)

    await _middleware(recorder)._persist(RECORD)

    assert seen == [RECORD]


async def test_a_failed_write_does_not_raise() -> None:
    async def recorder(record: RequestRecord) -> None:
        raise RuntimeError("the audit table is gone")

    await _middleware(recorder)._persist(RECORD)


async def test_nothing_is_written_without_a_recorder() -> None:
    await _middleware(None)._persist(RECORD)
