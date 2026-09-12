import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password
from app.models.item import Item
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import UserService
from tests.unit.fakes import (
    FakeItemRepository,
    FakeRoleRepository,
    FakeUserRepository,
    admin_role,
    user_role,
)


async def test_register_creates_user_when_email_free() -> None:
    repo = FakeUserRepository()
    service = UserService(repo, FakeItemRepository(), FakeRoleRepository())

    result = await service.register(UserCreate(email="a@b.com", password="secret123"))

    assert result.email == "a@b.com"
    assert result.hashed_password != "secret123"
    assert [user.email for user in repo.created] == ["a@b.com"]


async def test_register_rejects_duplicate_email() -> None:
    existing = User(email="a@b.com", hashed_password="x")
    repo = FakeUserRepository([existing])
    service = UserService(repo, FakeItemRepository(), FakeRoleRepository())

    with pytest.raises(ConflictError):
        await service.register(UserCreate(email="a@b.com", password="secret123"))

    assert repo.created == []


async def test_the_account_that_opens_an_empty_database_is_an_administrator() -> None:
    service = UserService(
        FakeUserRepository(), FakeItemRepository(), FakeRoleRepository()
    )

    first = await service.register(UserCreate(email="a@b.com", password="secret123"))

    assert first.role.name == UserRole.ADMIN


async def test_every_later_account_registers_as_a_plain_user() -> None:
    repo = FakeUserRepository()
    service = UserService(repo, FakeItemRepository(), FakeRoleRepository())
    await service.register(UserCreate(email="first@b.com", password="secret123"))

    second = await service.register(
        UserCreate(email="second@b.com", password="secret123")
    )

    assert second.role.name == UserRole.USER


async def test_a_closed_deployment_does_not_hand_admin_to_the_next_registration() -> (
    None
):
    repo = FakeUserRepository()
    items = FakeItemRepository()
    service = UserService(repo, items, FakeRoleRepository())
    only = await service.register(UserCreate(email="only@b.com", password="secret123"))
    await service.deactivate(only, "secret123")

    again = await service.register(UserCreate(email="next@b.com", password="secret123"))

    assert again.role.name == UserRole.USER


async def test_an_administrator_promotes_another_account() -> None:
    admin = User(id=1, email="admin@b.com", hashed_password="x", role=admin_role())
    target = User(id=2, email="other@b.com", hashed_password="x", role=user_role())
    repo = FakeUserRepository([admin, target])
    service = UserService(repo, FakeItemRepository(), FakeRoleRepository())

    result = await service.set_role(admin, 2, UserRole.ADMIN)

    assert result.role.name == UserRole.ADMIN
    assert repo.saved == [target]


async def test_an_administrator_cannot_change_their_own_role() -> None:
    admin = User(id=1, email="admin@b.com", hashed_password="x", role=admin_role())
    repo = FakeUserRepository([admin])
    service = UserService(repo, FakeItemRepository(), FakeRoleRepository())

    with pytest.raises(ForbiddenError):
        await service.set_role(admin, 1, UserRole.USER)

    assert admin.role.name == UserRole.ADMIN
    assert repo.saved == []


async def test_changing_the_role_of_a_missing_account_raises() -> None:
    admin = User(id=1, email="admin@b.com", hashed_password="x", role=admin_role())
    service = UserService(
        FakeUserRepository([admin]), FakeItemRepository(), FakeRoleRepository()
    )

    with pytest.raises(NotFoundError):
        await service.set_role(admin, 404, UserRole.ADMIN)


async def test_get_missing_user_raises() -> None:
    service = UserService(
        FakeUserRepository(), FakeItemRepository(), FakeRoleRepository()
    )

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
    service = UserService(
        RacingUserRepository(_UniqueViolation()),
        FakeItemRepository(),
        FakeRoleRepository(),
    )

    with pytest.raises(ConflictError, match="already registered"):
        await service.register(
            UserCreate(email="taken@example.com", password="secret123")
        )


async def test_an_address_change_that_loses_the_race_is_a_conflict() -> None:
    service = UserService(
        RacingUserRepository(_UniqueViolation()),
        FakeItemRepository(),
        FakeRoleRepository(),
    )
    user = User(id=1, email="before@example.com", hashed_password="x")

    with pytest.raises(ConflictError, match="already registered"):
        await service.update(user, UserUpdate(email="after@example.com"))


async def test_any_other_constraint_failure_is_still_a_crash() -> None:
    service = UserService(
        RacingUserRepository(_ForeignKeyViolation()),
        FakeItemRepository(),
        FakeRoleRepository(),
    )

    with pytest.raises(IntegrityError):
        await service.register(
            UserCreate(email="orphan@example.com", password="secret123")
        )


async def test_deactivating_an_account_takes_its_items_with_it() -> None:
    user = User(email="leaving@example.com", hashed_password=hash_password("secret123"))
    user.id = 3
    items = FakeItemRepository(
        [Item(title="mine", owner_id=3), Item(title="theirs", owner_id=4)]
    )
    users = FakeUserRepository([user])
    service = UserService(users, items, FakeRoleRepository())

    await service.deactivate(user, "secret123")

    assert users.deactivated == [user]
    assert [item.title for item in items.deleted] == ["mine"]
    assert await items.count_for_owner(4) == 1


async def test_deactivating_with_the_wrong_password_is_refused() -> None:
    user = User(email="leaving@example.com", hashed_password=hash_password("secret123"))
    user.id = 3
    items = FakeItemRepository([Item(title="mine", owner_id=3)])
    users = FakeUserRepository([user])
    service = UserService(users, items, FakeRoleRepository())

    with pytest.raises(ForbiddenError):
        await service.deactivate(user, "wrong-password")

    assert users.deactivated == []
    assert items.deleted == []
