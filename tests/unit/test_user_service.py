import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.user_service import UserService
from tests.unit.fakes import FakeUserRepository


async def test_register_creates_user_when_email_free() -> None:
    repo = FakeUserRepository()
    service = UserService(repo)

    result = await service.register(UserCreate(email="a@b.com", password="secret123"))

    assert result.email == "a@b.com"
    assert result.hashed_password != "secret123"
    assert [user.email for user in repo.created] == ["a@b.com"]


async def test_register_rejects_duplicate_email() -> None:
    existing = User(email="a@b.com", hashed_password="x")
    repo = FakeUserRepository([existing])
    service = UserService(repo)

    with pytest.raises(ConflictError):
        await service.register(UserCreate(email="a@b.com", password="secret123"))

    assert repo.created == []


async def test_get_missing_user_raises() -> None:
    service = UserService(FakeUserRepository())

    with pytest.raises(NotFoundError):
        await service.get(404)
