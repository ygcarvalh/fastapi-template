import asyncio
import sys
from datetime import timedelta

from app.core.config import get_settings
from app.db.session import dispose_engine
from app.jobs.maintenance import prune_audit_log


async def prune(days: int) -> int:
    removed = await prune_audit_log(timedelta(days=days))
    await dispose_engine()
    return removed


if __name__ == "__main__":
    retention_days = (
        int(sys.argv[1])
        if len(sys.argv) > 1
        else get_settings().audit_log_retention_days
    )
    print(f"removed {asyncio.run(prune(retention_days))} audit rows")
