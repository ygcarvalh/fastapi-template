from datetime import timedelta

import pytest

from app.core.exceptions import AuthError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.services.password_reset_service import PasswordResetService
from tests.unit.fakes import (
    FakeAccountMailer,
    FakeRefreshTokenRepository,
    FakeSingleUseTokenRepository,
    FakeUserRepository,
)

LIFETIME = timedelta(minutes=60)
EMAIL = "reader@example.com"
OLD_PASSWORD = "old-secret"
NEW_PASSWORD = "new-secret"


def _user() -> User:
    user = User(email=EMAIL, hashed_password=hash_password(OLD_PASSWORD))
    user.id = 1
    return user


def _service(
    user: User,
) -> tuple[PasswordResetService, FakeRefreshTokenRepository, FakeAccountMailer]:
    sessions = FakeRefreshTokenRepository()
    mailer = FakeAccountMailer()
    service = PasswordResetService(
        FakeUserRepository([user]),
        FakeSingleUseTokenRepository(),
        sessions,
        mailer,
        lifetime=LIFETIME,
    )
    return service, sessions, mailer


async def test_an_address_on_file_gets_a_link() -> None:
    service, _, mailer = _service(_user())

    await service.request(EMAIL)

    assert len(mailer.resets) == 1


async def test_an_address_nobody_registered_is_answered_with_silence() -> None:
    service, _, mailer = _service(_user())

    await service.request("stranger@example.com")

    assert mailer.resets == []


async def test_the_address_is_matched_however_it_was_typed() -> None:
    service, _, mailer = _service(_user())

    await service.request("  READER@Example.com ")

    assert len(mailer.resets) == 1


async def test_following_the_link_changes_the_password() -> None:
    user = _user()
    service, _, mailer = _service(user)
    await service.request(EMAIL)

    await service.confirm(mailer.resets[0][1], NEW_PASSWORD)

    assert verify_password(NEW_PASSWORD, user.hashed_password)


async def test_a_reset_signs_every_other_session_out() -> None:
    user = _user()
    service, sessions, mailer = _service(user)
    await service.request(EMAIL)

    await service.confirm(mailer.resets[0][1], NEW_PASSWORD)

    assert sessions.revoked_users == [user.id]


async def test_a_link_cannot_be_followed_twice() -> None:
    service, _, mailer = _service(_user())
    await service.request(EMAIL)
    token = mailer.resets[0][1]
    await service.confirm(token, NEW_PASSWORD)

    with pytest.raises(AuthError):
        await service.confirm(token, "another-secret")


async def test_asking_twice_retires_the_first_link() -> None:
    service, _, mailer = _service(_user())
    await service.request(EMAIL)
    first = mailer.resets[0][1]
    await service.request(EMAIL)

    with pytest.raises(AuthError):
        await service.confirm(first, NEW_PASSWORD)


async def test_a_token_nobody_issued_is_refused() -> None:
    service, _, _ = _service(_user())

    with pytest.raises(AuthError) as raised:
        await service.confirm("invented", NEW_PASSWORD)

    assert raised.value.code == "auth.invalidToken"


async def test_an_expired_link_is_refused() -> None:
    user = _user()
    mailer = FakeAccountMailer()
    service = PasswordResetService(
        FakeUserRepository([user]),
        FakeSingleUseTokenRepository(),
        FakeRefreshTokenRepository(),
        mailer,
        lifetime=timedelta(seconds=-1),
    )
    await service.request(EMAIL)

    with pytest.raises(AuthError):
        await service.confirm(mailer.resets[0][1], NEW_PASSWORD)
