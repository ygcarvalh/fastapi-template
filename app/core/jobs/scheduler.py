import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta

import structlog

logger = structlog.stdlib.get_logger("app.jobs")

JobRun = Callable[[], Awaitable[int]]


@dataclass(frozen=True)
class Job:
    name: str
    interval: timedelta
    run: JobRun


async def run_once(job: Job) -> int | None:
    started = time.perf_counter()
    try:
        rows = await job.run()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("job_failed", job=job.name, exc_info=True)
        return None
    logger.info(
        "job",
        job=job.name,
        rows=rows,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
    )
    return rows


class Scheduler:
    def __init__(
        self, jobs: Sequence[Job], *, startup_delay: timedelta = timedelta(seconds=0)
    ) -> None:
        self._jobs = list(jobs)
        self._startup_delay = startup_delay
        self._tasks: list[asyncio.Task[None]] = []

    @property
    def running(self) -> bool:
        return bool(self._tasks)

    async def start(self) -> None:
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(self._loop(job), name=f"job:{job.name}")
            for job in self._jobs
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _loop(self, job: Job) -> None:
        await asyncio.sleep(self._startup_delay.total_seconds())
        while True:
            await run_once(job)
            await asyncio.sleep(job.interval.total_seconds())
