from functools import lru_cache

from app.core.exceptions import AuthError
from app.core.security import create_access_token, hash_password, verify_password
from app.services.protocols import SupportsFindUserByEmail


@lru_cache(maxsize=1)
def _hash_for_absent_user() -> str:
    return hash_password("absent-user-constant-time-placeholder")


class AuthService:
    def __init__(self, repo: SupportsFindUserByEmail) -> None:
        self._repo = repo

    async def authenticate(self, email: str, password: str) -> str:
        user = await self._repo.get_by_email(email)
        hashed = user.hashed_password if user is not None else _hash_for_absent_user()
        password_matches = verify_password(password, hashed)
        if user is None or not password_matches:
            raise AuthError("Incorrect email or password")
        return create_access_token(str(user.id))
