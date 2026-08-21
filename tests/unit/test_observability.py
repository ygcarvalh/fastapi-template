from starlette.background import BackgroundTask, BackgroundTasks
from starlette.responses import Response

from app.core.observability import _after_response


def _noop() -> None: ...


def test_a_response_without_work_takes_the_task() -> None:
    response = Response()
    task = BackgroundTask(_noop)

    _after_response(response, task)

    assert response.background is task


def test_work_a_route_queued_is_kept() -> None:
    response = Response()
    theirs = BackgroundTask(_noop)
    response.background = theirs
    ours = BackgroundTask(_noop)

    _after_response(response, ours)

    queued = response.background
    assert isinstance(queued, BackgroundTasks)
    assert queued.tasks == [theirs, ours]
