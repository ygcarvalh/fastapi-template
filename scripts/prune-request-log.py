import asyncio
import sys
from datetime import timedelta

from app.core.config import get_settings
from app.db.session import dispose_engine
from app.jobs.maintenance import expire_tokens, prune_request_log


async def prune(days: int) -> tuple[int, int]:
    logs = await prune_request_log(timedelta(days=days))
    tokens = await expire_tokens()
    await dispose_engine()
    return logs, tokens


if __name__ == "__main__":
    retention_days = (
        int(sys.argv[1])
        if len(sys.argv) > 1
        else get_settings().request_log_retention_days
    )
    removed_logs, removed_tokens = asyncio.run(prune(retention_days))
    print(f"removed {removed_logs} request rows and {removed_tokens} expired tokens")
