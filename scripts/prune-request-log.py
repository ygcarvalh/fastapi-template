import asyncio
import sys
from datetime import UTC, datetime, timedelta

from app.db.session import dispose_engine, get_session_factory
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.request_log_repo import DELETE_BATCH_SIZE, RequestLogRepository
from app.services.request_log_service import RequestLogService

DEFAULT_RETENTION_DAYS = 30


async def prune(days: int) -> tuple[int, int]:
    retention = timedelta(days=days)
    logs = 0
    async with get_session_factory()() as session:
        service = RequestLogService(RequestLogRepository(session))
        while True:
            removed = await service.prune_batch(retention, DELETE_BATCH_SIZE)
            await session.commit()
            logs += removed
            if removed < DELETE_BATCH_SIZE:
                break

        tokens = await RefreshTokenRepository(session).delete_expired(datetime.now(UTC))
        await session.commit()

    await dispose_engine()
    return logs, tokens


if __name__ == "__main__":
    retention_days = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RETENTION_DAYS
    removed_logs, removed_tokens = asyncio.run(prune(retention_days))
    print(f"removed {removed_logs} request rows and {removed_tokens} expired tokens")
