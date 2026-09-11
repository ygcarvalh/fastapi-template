import time
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import (
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import User
from app.schemas.user import PasswordChange
from app.services.auth_service import AuthService
from tests.unit.fakes import FakeRefreshTokenRepository, FakeUserRepository

NOW = datetime.now(UTC)
EMAIL = "someone@example.com"
PASSWORD = "the-correct-password"


def _registered_user() -> User:
    user = User(email=EMAIL, hashed_password=hash_password(PASSWORD))
    user.id = 7
    return user


def _service(users: Sequence[User] = ()) -> AuthService:
    return AuthService(FakeUserRepository(users), FakeRefreshTokenRepository())


async def _time_rejected_login(users: Sequence[User]) -> tuple[float, str]:
    service = _service(users)
    start = time.perf_counter()
    with pytest.raises(AuthError) as caught:
        await service.authenticate(EMAIL, "wrong-password")
    return time.perf_counter() - start, caught.value.detail


async def test_authenticate_returns_a_token_pair_for_the_right_password() -> None:
    service = _service([_registered_user()])

    pair = await service.authenticate(EMAIL, PASSWORD)

    assert decode_access_token(pair.access_token) == "7"
    assert decode_refresh_token(pair.refresh_token) == "7"


async def test_a_stored_refresh_token_buys_a_new_access_token() -> None:
    service = _service([_registered_user()])
    issued = await service.authenticate(EMAIL, PASSWORD)

    refreshed = await service.refresh(issued.refresh_token)

    assert decode_access_token(refreshed.access_token) == "7"
    assert refreshed.refresh_token == issued.refresh_token


async def test_a_refresh_token_nobody_issued_is_refused() -> None:
    service = _service([_registered_user()])

    with pytest.raises(AuthError):
        await service.refresh(create_refresh_token("7"))


async def test_signing_out_retires_the_refresh_token() -> None:
    service = _service([_registered_user()])
    issued = await service.authenticate(EMAIL, PASSWORD)

    await service.logout(issued.refresh_token)

    with pytest.raises(AuthError):
        await service.refresh(issued.refresh_token)


async def test_signing_out_twice_is_harmless() -> None:
    service = _service([_registered_user()])
    issued = await service.authenticate(EMAIL, PASSWORD)

    await service.logout(issued.refresh_token)
    await service.logout(issued.refresh_token)


async def test_revoking_sessions_closes_every_token_at_once() -> None:
    user = _registered_user()
    service = _service([user])
    first = await service.authenticate(EMAIL, PASSWORD)
    second = await service.authenticate(EMAIL, PASSWORD)

    revoked = await service.revoke_sessions(user)

    assert revoked == 2
    for pair in (first, second):
        with pytest.raises(AuthError):
            await service.refresh(pair.refresh_token)


async def test_a_token_stored_against_another_account_is_refused() -> None:
    user = _registered_user()
    tokens = FakeRefreshTokenRepository()
    service = AuthService(FakeUserRepository([user]), tokens)
    issued = await service.authenticate(EMAIL, PASSWORD)
    stored = await tokens.get_active(hash_refresh_token(issued.refresh_token), NOW)
    assert stored is not None
    stored.user_id = 999

    with pytest.raises(AuthError):
        await service.refresh(issued.refresh_token)


async def test_refresh_rejects_a_non_numeric_subject() -> None:
    service = _service([_registered_user()])

    with pytest.raises(AuthError):
        await service.refresh(create_refresh_token("not-a-user-id"))


async def test_refresh_rejects_a_subject_with_no_matching_user() -> None:
    users = FakeUserRepository()
    tokens = FakeRefreshTokenRepository()
    service = AuthService(users, tokens)
    ghost = User(email="ghost@example.com", hashed_password=hash_password(PASSWORD))
    ghost.id = 404
    issued = await AuthService(FakeUserRepository([ghost]), tokens).authenticate(
        "ghost@example.com", PASSWORD
    )

    with pytest.raises(AuthError):
        await service.refresh(issued.refresh_token)


async def test_absent_user_login_costs_as_much_as_wrong_password() -> None:
    absent_duration, _ = await _time_rejected_login([])
    present_duration, _ = await _time_rejected_login([_registered_user()])

    assert absent_duration >= present_duration * 0.5


async def test_absent_user_and_wrong_password_are_indistinguishable() -> None:
    _, absent_detail = await _time_rejected_login([])
    _, present_detail = await _time_rejected_login([_registered_user()])

    assert absent_detail == present_detail


async def test_changing_the_password_rehashes_and_signs_every_device_out() -> None:
    user = _registered_user()
    service = _service([user])
    pair = await service.authenticate(EMAIL, PASSWORD)

    await service.change_password(
        user, PasswordChange(current_password=PASSWORD, new_password="another-one")
    )

    assert verify_password("another-one", user.hashed_password)
    with pytest.raises(AuthError):
        await service.refresh(pair.refresh_token)


async def test_changing_the_password_needs_the_current_one() -> None:
    user = _registered_user()
    service = _service([user])
    pair = await service.authenticate(EMAIL, PASSWORD)

    with pytest.raises(ForbiddenError):
        await service.change_password(
            user,
            PasswordChange(current_password="not-it", new_password="another-one"),
        )

    assert verify_password(PASSWORD, user.hashed_password)
    assert await service.refresh(pair.refresh_token)
