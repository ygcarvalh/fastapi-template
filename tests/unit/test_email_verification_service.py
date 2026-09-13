from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import AuthError
from app.core.security import hash_single_use_token
from app.models.single_use_token import SingleUseToken, TokenPurpose
from app.models.user import User
from app.services.email_verification_service import EmailVerificationService
from tests.unit.fakes import (
    FakeAccountMailer,
    FakeSingleUseTokenRepository,
    FakeUserRepository,
)

LIFETIME = timedelta(hours=48)


def _user(verified: bool = False) -> User:
    user = User(email="reader@example.com", hashed_password="x")
    user.id = 1
    user.email_verified_at = datetime.now(UTC) if verified else None
    return user


def _service(
    user: User,
) -> tuple[EmailVerificationService, FakeSingleUseTokenRepository, FakeAccountMailer]:
    tokens = FakeSingleUseTokenRepository()
    mailer = FakeAccountMailer()
    service = EmailVerificationService(
        FakeUserRepository([user]), tokens, mailer, lifetime=LIFETIME
    )
    return service, tokens, mailer


async def test_asking_for_a_confirmation_mails_a_token() -> None:
    user = _user()
    service, tokens, mailer = _service(user)

    await service.request(user)

    assert len(mailer.verifications) == 1
    _, token, expires_at = mailer.verifications[0]
    assert await tokens.get_active(
        hash_single_use_token(token),
        TokenPurpose.EMAIL_VERIFICATION,
        datetime.now(UTC),
    )
    assert expires_at > datetime.now(UTC)


async def test_the_token_is_stored_hashed_and_never_in_the_clear() -> None:
    user = _user()
    service, tokens, mailer = _service(user)

    await service.request(user)
    _, token, _ = mailer.verifications[0]

    stored = await tokens.get_active(
        hash_single_use_token(token),
        TokenPurpose.EMAIL_VERIFICATION,
        datetime.now(UTC),
    )
    assert stored is not None
    assert stored.token_hash != token


async def test_an_account_already_confirmed_is_sent_nothing() -> None:
    user = _user(verified=True)
    service, _, mailer = _service(user)

    await service.request(user)

    assert mailer.verifications == []


async def test_asking_again_retires_the_link_already_sent() -> None:
    user = _user()
    service, tokens, mailer = _service(user)
    await service.request(user)
    first = mailer.verifications[0][1]

    await service.request(user)

    assert (
        await tokens.get_active(
            hash_single_use_token(first),
            TokenPurpose.EMAIL_VERIFICATION,
            datetime.now(UTC),
        )
        is None
    )


async def test_confirming_stamps_the_account() -> None:
    user = _user()
    service, _, mailer = _service(user)
    await service.request(user)

    confirmed = await service.confirm(mailer.verifications[0][1])

    assert confirmed.email_verified_at is not None


async def test_a_link_cannot_be_followed_twice() -> None:
    user = _user()
    service, _, mailer = _service(user)
    await service.request(user)
    token = mailer.verifications[0][1]
    await service.confirm(token)

    with pytest.raises(AuthError):
        await service.confirm(token)


async def test_a_token_nobody_issued_is_refused() -> None:
    service, _, _ = _service(_user())

    with pytest.raises(AuthError) as raised:
        await service.confirm("invented")

    assert raised.value.code == "auth.invalidToken"


async def test_an_expired_link_is_refused() -> None:
    user = _user()
    tokens = FakeSingleUseTokenRepository()
    service = EmailVerificationService(
        FakeUserRepository([user]),
        tokens,
        FakeAccountMailer(),
        lifetime=LIFETIME,
    )
    await tokens.create(
        SingleUseToken(
            token_hash=hash_single_use_token("stale"),
            user_id=user.id,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )

    with pytest.raises(AuthError):
        await service.confirm("stale")


async def test_a_reset_token_cannot_confirm_an_address() -> None:
    user = _user()
    tokens = FakeSingleUseTokenRepository()
    service = EmailVerificationService(
        FakeUserRepository([user]), tokens, FakeAccountMailer(), lifetime=LIFETIME
    )
    await tokens.create(
        SingleUseToken(
            token_hash=hash_single_use_token("borrowed"),
            user_id=user.id,
            purpose=TokenPurpose.PASSWORD_RESET,
            expires_at=datetime.now(UTC) + LIFETIME,
        )
    )

    with pytest.raises(AuthError):
        await service.confirm("borrowed")


async def test_asking_twice_in_a_row_sends_one_message() -> None:
    user = _user()
    mailer = FakeAccountMailer()
    service = EmailVerificationService(
        FakeUserRepository([user]),
        FakeSingleUseTokenRepository(),
        mailer,
        lifetime=LIFETIME,
        resend_cooldown=timedelta(minutes=1),
    )

    await service.request(user)
    await service.request(user)

    assert len(mailer.verifications) == 1
