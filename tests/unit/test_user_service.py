from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ConflictError
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.user_service import UserService


async def test_register_creates_user_when_email_free() -> None:
    repo = AsyncMock()
    repo.get_by_email.return_value = None
    repo.create.side_effect = lambda user: user

    service = UserService(repo)
    result = await service.register(UserCreate(email="a@b.com", password="secret123"))

    assert result.email == "a@b.com"
    assert result.hashed_password != "secret123"
    repo.create.assert_awaited_once()


async def test_register_rejects_duplicate_email() -> None:
    repo = AsyncMock()
    repo.get_by_email.return_value = User(email="a@b.com", hashed_password="x")

    service = UserService(repo)
    with pytest.raises(ConflictError):
        await service.register(UserCreate(email="a@b.com", password="secret123"))
