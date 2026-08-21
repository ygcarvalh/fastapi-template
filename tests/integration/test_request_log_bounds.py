from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.request_log import RequestLog
from app.models.user import User
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.request_log_repo import MAX_COUNTED_ROWS, RequestLogRepository
from app.schemas.request_log import RequestLogQuery


async def _seed(session: AsyncSession, count: int, *, days_old: int = 0) -> None:
    created = datetime.now(UTC) - timedelta(days=days_old)
    session.add_all(
        RequestLog(
            request_id=f"row-{index}-{days_old}",
            method="GET",
            path="/api/v1/items",
            status_code=200,
            duration_ms=1.0,
            created_at=created,
        )
        for index in range(count)
    )
    await session.flush()


async def test_the_count_stops_at_the_cap(db_session: AsyncSession) -> None:
    await _seed(db_session, MAX_COUNTED_ROWS + 5)
    repo = RequestLogRepository(db_session)

    counted = await repo.count(RequestLogQuery())

    assert counted == MAX_COUNTED_ROWS + 1


async def test_a_small_table_is_counted_exactly(db_session: AsyncSession) -> None:
    await _seed(db_session, 3)
    repo = RequestLogRepository(db_session)

    assert await repo.count(RequestLogQuery()) == 3


async def test_a_retention_run_deletes_in_batches(db_session: AsyncSession) -> None:
    await _seed(db_session, 5, days_old=40)
    await _seed(db_session, 2)
    repo = RequestLogRepository(db_session)
    cutoff = datetime.now(UTC) - timedelta(days=30)

    first = await repo.delete_batch_created_before(cutoff, batch_size=2)
    second = await repo.delete_batch_created_before(cutoff, batch_size=2)
    third = await repo.delete_batch_created_before(cutoff, batch_size=2)

    assert (first, second, third) == (2, 2, 1)
    assert await repo.count(RequestLogQuery()) == 2


async def test_expired_tokens_are_swept(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    owner = User(email="sweeper@example.com", hashed_password="x")
    db_session.add(owner)
    await db_session.flush()
    db_session.add_all(
        [
            RefreshToken(
                token_hash="a" * 64,
                user_id=owner.id,
                expires_at=now - timedelta(days=1),
            ),
            RefreshToken(
                token_hash="b" * 64,
                user_id=owner.id,
                expires_at=now + timedelta(days=1),
            ),
        ]
    )
    await db_session.flush()

    removed = await RefreshTokenRepository(db_session).delete_expired(now)

    assert removed == 1
