import asyncio
import sys
from datetime import timedelta

from app.core.audit.context import audit_suppressed
from app.core.config import get_settings
from app.db.session import dispose_engine, get_session_factory
from app.repositories.audit_log_repo import DELETE_BATCH_SIZE, AuditLogRepository
from app.services.audit_log_service import AuditLogService


async def prune(days: int) -> int:
    retention = timedelta(days=days)
    removed_total = 0
    with audit_suppressed():
        async with get_session_factory()() as session:
            service = AuditLogService(AuditLogRepository(session))
            while True:
                removed = await service.prune_batch(retention, DELETE_BATCH_SIZE)
                await session.commit()
                removed_total += removed
                if removed < DELETE_BATCH_SIZE:
                    break

    await dispose_engine()
    return removed_total


if __name__ == "__main__":
    retention_days = (
        int(sys.argv[1])
        if len(sys.argv) > 1
        else get_settings().audit_log_retention_days
    )
    print(f"removed {asyncio.run(prune(retention_days))} audit rows")
