from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate


class UserService:
    def __init__(self, repo: UserRepository) -> None:
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
