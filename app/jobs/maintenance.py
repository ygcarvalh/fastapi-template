from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.context import audit_suppressed
from app.core.constants import DELETE_BATCH_SIZE
from app.db.session import get_session_factory
from app.jobs.locking import held_by_one_replica
from app.repositories.audit_log_repo import AuditLogRepository
from app.repositories.idempotency_repo import IdempotencyRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.request_log_repo import RequestLogRepository
from app.repositories.single_use_token_repo import SingleUseTokenRepository
from app.services.audit_log_service import AuditLogService
from app.services.idempotency_service import IdempotencyService
from app.services.request_log_service import RequestLogService

PRUNE_AUDIT_LOG = "prune-audit-log"
PRUNE_REQUEST_LOG = "prune-request-log"
PRUNE_IDEMPOTENCY_KEYS = "prune-idempotency-keys"
EXPIRE_TOKENS = "expire-tokens"

Work = Callable[[], Awaitable[int]]
PruneBatch = Callable[[timedelta, int], Awaitable[int]]


# One session for the whole drain: each batch commits in turn, so a job that
# dies partway through has already persisted every batch before it.
async def _drain(
    session: AsyncSession, prune_batch: PruneBatch, retention: timedelta
) -> int:
    removed = 0
    while True:
        batch = await prune_batch(retention, DELETE_BATCH_SIZE)
        await session.commit()
        removed += batch
        if batch < DELETE_BATCH_SIZE:
            return removed


async def prune_audit_log(retention: timedelta) -> int:
    with audit_suppressed():
        async with get_session_factory()() as session:
            service = AuditLogService(AuditLogRepository(session))
            return await _drain(session, service.prune_batch, retention)


async def prune_request_log(retention: timedelta) -> int:
    async with get_session_factory()() as session:
        service = RequestLogService(RequestLogRepository(session))
        return await _drain(session, service.prune_batch, retention)


async def prune_idempotency_keys(retention: timedelta) -> int:
    async with get_session_factory()() as session:
        service = IdempotencyService(IdempotencyRepository(session))
        return await _drain(session, service.prune_batch, retention)


async def expire_tokens() -> int:
    now = datetime.now(UTC)
    async with get_session_factory()() as session:
        removed = await RefreshTokenRepository(session).delete_expired(now)
        removed += await SingleUseTokenRepository(session).delete_expired(now)
        await session.commit()
        return removed


async def once_across_replicas(name: str, work: Work) -> int:
    async with (
        get_session_factory()() as session,
        held_by_one_replica(session, name) as acquired,
    ):
        if not acquired:
            return 0
        return await work()
