import time

import pytest

from app.core.exceptions import AuthError
from app.core.security import hash_password
from app.models.user import User
from app.services.auth_service import AuthService


class _StubUserRepository:
    def __init__(self, user: User | None) -> None:
        self._user = user

    async def get_by_email(self, email: str) -> User | None:
        return self._user

    async def get(self, user_id: int) -> User | None:
        return self._user

    async def create(self, user: User) -> User:
        return user


async def _time_rejected_login(user: User | None) -> tuple[float, str]:
    service = AuthService(_StubUserRepository(user))
    start = time.perf_counter()
    with pytest.raises(AuthError) as caught:
        await service.authenticate("someone@example.com", "wrong-password")
    return time.perf_counter() - start, caught.value.detail


def _existing_user() -> User:
    return User(
        email="someone@example.com",
        hashed_password=hash_password("the-correct-password"),
    )


async def test_absent_user_login_costs_as_much_as_wrong_password() -> None:
    absent_duration, _ = await _time_rejected_login(None)
    present_duration, _ = await _time_rejected_login(_existing_user())

    assert absent_duration >= present_duration * 0.5


async def test_absent_user_and_wrong_password_are_indistinguishable() -> None:
    _, absent_detail = await _time_rejected_login(None)
    _, present_detail = await _time_rejected_login(_existing_user())

    assert absent_detail == present_detail
