from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.user import User

STAMPED_EMAIL = "stamped@example.com"
BUMPED_EMAIL = "bumped@example.com"


async def test_new_rows_get_both_timestamps(
    db_session: AsyncSession,
) -> None:
    user = User(email=STAMPED_EMAIL, hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    assert user.created_at is not None
    assert user.updated_at == user.created_at


async def test_updated_at_advances_on_a_later_transaction(
    engine: AsyncEngine,
) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with factory() as session:
            user = User(email=BUMPED_EMAIL, hashed_password="x")
            session.add(user)
            await session.commit()
            created_at = user.created_at

        async with factory() as session:
            stored = await session.execute(
                select(User).where(User.email == BUMPED_EMAIL)
            )
            found = stored.scalar_one()
            found.hashed_password = "rotated"
            await session.commit()
            await session.refresh(found)

            assert found.created_at == created_at
            assert found.updated_at > created_at
    finally:
        async with factory() as session:
            await session.execute(delete(User).where(User.email == BUMPED_EMAIL))
            await session.commit()
