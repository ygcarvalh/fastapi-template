from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from zlib import crc32

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

LOCK = text("SELECT pg_try_advisory_lock(:key)")
UNLOCK = text("SELECT pg_advisory_unlock(:key)")

SIGNED_32_BIT_OFFSET = 2**31


def lock_key(name: str) -> int:
    return crc32(name.encode()) - SIGNED_32_BIT_OFFSET


@asynccontextmanager
async def held_by_one_replica(session: AsyncSession, name: str) -> AsyncIterator[bool]:
    key = lock_key(name)
    acquired = bool((await session.execute(LOCK, {"key": key})).scalar_one())
    try:
        yield acquired
    finally:
        if acquired:
            await session.execute(UNLOCK, {"key": key})
