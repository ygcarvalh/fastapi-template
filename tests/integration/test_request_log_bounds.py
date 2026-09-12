from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.request_log import RequestLog
from app.models.user import User
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.request_log_repo import RequestLogRepository
from app.schemas.request_log import RequestLogQuery, encode_cursor


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


async def test_a_page_reads_one_row_past_its_limit(db_session: AsyncSession) -> None:
    await _seed(db_session, 5)
    repo = RequestLogRepository(db_session)

    found = await repo.list_page(RequestLogQuery(limit=2))

    # The extra row is how the service knows there is another page, without
    # anyone counting the table.
    assert len(found) == 3


async def test_a_cursor_walks_past_the_rows_already_read(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session, 5)
    repo = RequestLogRepository(db_session)

    first = await repo.list_page(RequestLogQuery(limit=2))
    edge = first[1]
    rest = await repo.list_page(
        RequestLogQuery(limit=2, cursor=encode_cursor(edge.created_at, edge.id))
    )

    assert next(entry.id for entry in rest) < edge.id


async def test_a_retention_run_deletes_in_batches(db_session: AsyncSession) -> None:
    await _seed(db_session, 5, days_old=40)
    await _seed(db_session, 2)
    repo = RequestLogRepository(db_session)
    cutoff = datetime.now(UTC) - timedelta(days=30)

    first = await repo.delete_batch_created_before(cutoff, batch_size=2)
    second = await repo.delete_batch_created_before(cutoff, batch_size=2)
    third = await repo.delete_batch_created_before(cutoff, batch_size=2)

    assert (first, second, third) == (2, 2, 1)
    assert len(await repo.list_page(RequestLogQuery(limit=50))) == 2


async def test_expired_tokens_are_swept(
    db_session: AsyncSession, plain_role_id: int
) -> None:
    now = datetime.now(UTC)
    owner = User(
        email="sweeper@example.com", hashed_password="x", role_id=plain_role_id
    )
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
