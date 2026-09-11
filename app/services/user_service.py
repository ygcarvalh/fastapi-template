from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.protocols import ItemRepositoryProtocol, UserRepositoryProtocol

EMAIL_TAKEN = "Email already registered"
UNIQUE_VIOLATION = "23505"


# Only a unique violation is a conflict. A foreign key or a not-null failure is
# a bug on our side and stays a 500.
def _as_conflict(error: IntegrityError) -> Exception:
    if getattr(error.orig, "sqlstate", None) == UNIQUE_VIOLATION:
        return ConflictError(EMAIL_TAKEN)
    return error


class UserService:
    def __init__(
        self, repo: UserRepositoryProtocol, items: ItemRepositoryProtocol
    ) -> None:
        self._repo = repo
        self._items = items

    async def register(self, data: UserCreate) -> User:
        if await self._repo.get_by_email(data.email) is not None:
            raise ConflictError(EMAIL_TAKEN)
        user = User(
            email=data.email,
            name=data.name,
            hashed_password=hash_password(data.password),
        )
        try:
            return await self._repo.create(user)
        except IntegrityError as error:
            raise _as_conflict(error) from error

    async def get(self, user_id: int) -> User:
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def update(self, user: User, data: UserUpdate) -> User:
        fields = data.model_dump(exclude_unset=True)
        email = fields.get("email")
        if email is not None and email != user.email:
            if await self._repo.get_by_email(email) is not None:
                raise ConflictError(EMAIL_TAKEN)
            user.email = email
        if "name" in fields:
            user.name = fields["name"]
        try:
            return await self._repo.save(user)
        except IntegrityError as error:
            raise _as_conflict(error) from error

    async def list_all(self, limit: int, offset: int) -> tuple[Sequence[User], int]:
        users = await self._repo.list_all(limit, offset)
        total = await self._repo.count_all()
        return users, total

    # What the account owns goes with it, so a deactivated address that
    # registers again starts empty.
    async def deactivate(self, user: User, password: str) -> None:
        if not verify_password(password, user.hashed_password):
            raise ForbiddenError("Password is incorrect")
        await self._items.soft_delete_for_owner(user.id)
        await self._repo.soft_delete(user)
