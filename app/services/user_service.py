from collections.abc import Sequence

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.protocols import UserRepositoryProtocol


class UserService:
    def __init__(self, repo: UserRepositoryProtocol) -> None:
        self._repo = repo

    async def register(self, data: UserCreate) -> User:
        if await self._repo.get_by_email(data.email) is not None:
            raise ConflictError("Email already registered")
        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
        )
        return await self._repo.create(user)

    async def get(self, user_id: int) -> User:
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    async def list_all(self, limit: int, offset: int) -> tuple[Sequence[User], int]:
        users = await self._repo.list_all(limit, offset)
        total = await self._repo.count_all()
        return users, total

    async def deactivate(self, user: User) -> None:
        await self._repo.soft_delete(user)
