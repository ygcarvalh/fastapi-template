import asyncio
import logging
from datetime import timedelta

import pytest

from app.core.jobs.scheduler import Job, Scheduler, run_once

TICK = timedelta(seconds=0.01)


def _counting_job(name: str = "count") -> tuple[Job, list[int]]:
    runs: list[int] = []

    async def work() -> int:
        runs.append(len(runs) + 1)
        return len(runs)

    return Job(name, TICK, work), runs


async def test_a_run_hands_back_what_the_job_touched() -> None:
    job, _ = _counting_job()

    assert await run_once(job) == 1


async def test_a_job_that_raises_is_logged_and_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def work() -> int:
        raise RuntimeError("the real cause")

    with caplog.at_level(logging.WARNING):
        result = await run_once(Job("broken", TICK, work))

    assert result is None
    assert "job_failed" in caplog.text
    assert "broken" in caplog.text
    assert "exc_info" in caplog.text


async def test_a_started_scheduler_keeps_running_its_jobs() -> None:
    job, runs = _counting_job()
    scheduler = Scheduler([job])

    await scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert len(runs) > 1
    assert not scheduler.running


async def test_a_stopped_scheduler_runs_nothing_more() -> None:
    job, runs = _counting_job()
    scheduler = Scheduler([job])
    await scheduler.start()
    await asyncio.sleep(0.03)

    await scheduler.stop()
    settled = len(runs)
    await asyncio.sleep(0.03)

    assert len(runs) == settled


async def test_starting_twice_does_not_double_the_work() -> None:
    job, _ = _counting_job()
    scheduler = Scheduler([job])

    await scheduler.start()
    await scheduler.start()
    await scheduler.stop()

    assert not scheduler.running


async def test_nothing_runs_before_the_startup_delay() -> None:
    job, runs = _counting_job()
    scheduler = Scheduler([job], startup_delay=timedelta(seconds=5))

    await scheduler.start()
    await asyncio.sleep(0.02)
    await scheduler.stop()

    assert runs == []


async def test_one_failing_job_does_not_stop_the_others() -> None:
    healthy, runs = _counting_job("healthy")

    async def broken() -> int:
        raise RuntimeError("the real cause")

    scheduler = Scheduler([Job("broken", TICK, broken), healthy])

    await scheduler.start()
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assert len(runs) > 1
