from app.core.exceptions import AuthError
from app.core.security import create_access_token, verify_password
from app.repositories.user_repo import UserRepository


class AuthService:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def authenticate(self, email: str, password: str) -> str:
        user = await self._repo.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise AuthError("Incorrect email or password")
        return create_access_token(str(user.id))
