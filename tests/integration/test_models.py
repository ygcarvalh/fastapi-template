from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.user import User


async def test_user_owns_items(db_session: AsyncSession) -> None:
    user = User(email="owner@example.com", hashed_password="x")
    user.items.append(Item(title="First"))
    db_session.add(user)
    await db_session.flush()

    loaded = (
        await db_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    assert loaded.id is not None
    assert loaded.created_at is not None
    assert len(loaded.items) == 1
    assert loaded.items[0].owner_id == loaded.id
