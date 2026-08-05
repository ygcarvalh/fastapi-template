import time
from collections.abc import Sequence

import pytest

from app.core.exceptions import AuthError
from app.core.security import (
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
)
from app.models.user import User
from app.services.auth_service import AuthService
from tests.unit.fakes import FakeUserRepository

EMAIL = "someone@example.com"
PASSWORD = "the-correct-password"


def _registered_user() -> User:
    user = User(email=EMAIL, hashed_password=hash_password(PASSWORD))
    user.id = 7
    return user


async def _time_rejected_login(users: Sequence[User]) -> tuple[float, str]:
    service = AuthService(FakeUserRepository(users))
    start = time.perf_counter()
    with pytest.raises(AuthError) as caught:
        await service.authenticate(EMAIL, "wrong-password")
    return time.perf_counter() - start, caught.value.detail


async def test_authenticate_returns_a_token_pair_for_the_right_password() -> None:
    service = AuthService(FakeUserRepository([_registered_user()]))

    pair = await service.authenticate(EMAIL, PASSWORD)

    assert decode_access_token(pair.access_token) == "7"
    assert decode_refresh_token(pair.refresh_token) == "7"


async def test_refresh_rejects_a_non_numeric_subject() -> None:
    service = AuthService(FakeUserRepository([_registered_user()]))

    with pytest.raises(AuthError):
        await service.refresh(create_refresh_token("not-a-user-id"))


async def test_refresh_rejects_a_subject_with_no_matching_user() -> None:
    service = AuthService(FakeUserRepository())

    with pytest.raises(AuthError):
        await service.refresh(create_refresh_token("404"))


async def test_absent_user_login_costs_as_much_as_wrong_password() -> None:
    absent_duration, _ = await _time_rejected_login([])
    present_duration, _ = await _time_rejected_login([_registered_user()])

    assert absent_duration >= present_duration * 0.5


async def test_absent_user_and_wrong_password_are_indistinguishable() -> None:
    _, absent_detail = await _time_rejected_login([])
    _, present_detail = await _time_rejected_login([_registered_user()])

    assert absent_detail == present_detail
