from functools import lru_cache
from typing import NamedTuple

from app.core.exceptions import AuthError
from app.core.security import (
    INVALID_CREDENTIALS,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.services.protocols import UserRepositoryProtocol


class TokenPair(NamedTuple):
    access_token: str
    refresh_token: str


@lru_cache(maxsize=1)
def _hash_for_absent_user() -> str:
    return hash_password("absent-user-constant-time-placeholder")


def _issue(subject: str) -> TokenPair:
    return TokenPair(create_access_token(subject), create_refresh_token(subject))


class AuthService:
    def __init__(self, repo: UserRepositoryProtocol) -> None:
        self._repo = repo

    async def authenticate(self, email: str, password: str) -> TokenPair:
        user = await self._repo.get_by_email(email)
        hashed = user.hashed_password if user is not None else _hash_for_absent_user()
        password_matches = verify_password(password, hashed)
        if user is None or not password_matches:
            raise AuthError("Incorrect email or password")
        return _issue(str(user.id))

    async def refresh(self, refresh_token: str) -> TokenPair:
        subject = decode_refresh_token(refresh_token)
        try:
            user_id = int(subject)
        except ValueError as exc:
            raise AuthError(INVALID_CREDENTIALS) from exc

        user = await self._repo.get(user_id)
        if user is None:
            raise AuthError(INVALID_CREDENTIALS)
        return _issue(str(user.id))
