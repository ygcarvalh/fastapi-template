import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
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


class _UniqueViolation(Exception):
    sqlstate = "23505"


class _ForeignKeyViolation(Exception):
    sqlstate = "23503"


def _integrity_error(cause: Exception) -> IntegrityError:
    return IntegrityError("INSERT", {}, cause)


class RacingUserRepository(FakeUserRepository):
    """A repository whose write loses the race the check could not close."""

    def __init__(self, cause: Exception) -> None:
        super().__init__()
        self._cause = cause

    async def create(self, user: User) -> User:
        raise _integrity_error(self._cause)

    async def save(self, user: User) -> User:
        raise _integrity_error(self._cause)


async def test_a_registration_that_loses_the_race_is_a_conflict() -> None:
    service = UserService(RacingUserRepository(_UniqueViolation()))

    with pytest.raises(ConflictError, match="already registered"):
        await service.register(
            UserCreate(email="taken@example.com", password="secret123")
        )


async def test_an_address_change_that_loses_the_race_is_a_conflict() -> None:
    service = UserService(RacingUserRepository(_UniqueViolation()))
    user = User(id=1, email="before@example.com", hashed_password="x")

    with pytest.raises(ConflictError, match="already registered"):
        await service.update(user, UserUpdate(email="after@example.com"))


async def test_any_other_constraint_failure_is_still_a_crash() -> None:
    service = UserService(RacingUserRepository(_ForeignKeyViolation()))

    with pytest.raises(IntegrityError):
        await service.register(
            UserCreate(email="orphan@example.com", password="secret123")
        )
