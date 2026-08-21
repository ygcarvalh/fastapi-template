from collections.abc import Sequence

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import PasswordChange, UserCreate, UserUpdate
from app.services.protocols import UserRepositoryProtocol


class UserService:
    def __init__(self, repo: UserRepositoryProtocol) -> None:
        self._repo = repo

    async def register(self, data: UserCreate) -> User:
        if await self._repo.get_by_email(data.email) is not None:
            raise ConflictError("Email already registered")
        user = User(
            email=data.email,
            name=data.name,
            hashed_password=hash_password(data.password),
        )
        return await self._repo.create(user)

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
                raise ConflictError("Email already registered")
            user.email = email
        if "name" in fields:
            user.name = fields["name"]
        return await self._repo.save(user)

    # A valid access token is not enough, or a leaked one would be a takeover.
    # Tokens minted before the change keep working: nothing is stored to
    # compare them against.
    async def change_password(self, user: User, data: PasswordChange) -> None:
        if not verify_password(data.current_password, user.hashed_password):
            raise ForbiddenError("Current password is incorrect")
        user.hashed_password = hash_password(data.new_password)
        await self._repo.save(user)

    async def list_all(self, limit: int, offset: int) -> tuple[Sequence[User], int]:
        users = await self._repo.list_all(limit, offset)
        total = await self._repo.count_all()
        return users, total

    async def deactivate(self, user: User) -> None:
        await self._repo.soft_delete(user)
