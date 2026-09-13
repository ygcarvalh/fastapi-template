from datetime import UTC, datetime

from app.core.mail.message import Mail
from app.models.user import User
from app.models.user_preferences import UserPreferences
from app.services.account_mailer import AccountMailer
from tests.unit.fakes import FakePreferencesRepository

BASE_URL = "https://app.example.com"
EXPIRES_AT = datetime(2026, 6, 1, 15, 30, tzinfo=UTC)
TOKEN = "a-token/with+characters"


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[Mail] = []

    async def send(self, mail: Mail) -> None:
        self.sent.append(mail)


def _user(name: str | None = "Ada") -> User:
    user = User(email="reader@example.com", name=name, hashed_password="x")
    user.id = 1
    return user


def _preferences(locale: str, timezone: str = "UTC") -> FakePreferencesRepository:
    return FakePreferencesRepository(
        UserPreferences(user_id=1, locale=locale, theme="system", timezone=timezone)
    )


def _mailer(
    preferences: FakePreferencesRepository,
) -> tuple[AccountMailer, RecordingSender]:
    sender = RecordingSender()
    return AccountMailer(sender, preferences, base_url=BASE_URL), sender


async def test_the_mail_speaks_the_language_the_account_saved() -> None:
    mailer, sender = _mailer(_preferences("pt-BR"))

    await mailer.send_password_reset(_user(), TOKEN, EXPIRES_AT)

    assert sender.sent[0].subject == "Redefina sua senha"


async def test_an_account_that_saved_nothing_reads_the_default() -> None:
    mailer, sender = _mailer(FakePreferencesRepository())

    await mailer.send_password_reset(_user(), TOKEN, EXPIRES_AT)

    assert sender.sent[0].subject == "Reset your password"


async def test_a_language_this_service_does_not_speak_reads_the_default() -> None:
    mailer, sender = _mailer(_preferences("de-DE"))

    await mailer.send_email_verification(_user(), TOKEN, EXPIRES_AT)

    assert sender.sent[0].subject == "Confirm your email address"


async def test_the_deadline_is_written_in_the_zone_the_account_saved() -> None:
    mailer, sender = _mailer(_preferences("en-US", "America/Sao_Paulo"))

    await mailer.send_password_reset(_user(), TOKEN, EXPIRES_AT)

    assert "2026-06-01 12:30 -03" in sender.sent[0].body


async def test_the_link_carries_the_token_escaped() -> None:
    mailer, sender = _mailer(_preferences("en-US"))

    await mailer.send_email_verification(_user(), TOKEN, EXPIRES_AT)

    assert (
        f"{BASE_URL}/verify-email?token=a-token%2Fwith%2Bcharacters"
        in sender.sent[0].body
    )


async def test_the_reset_link_points_at_the_reset_screen() -> None:
    mailer, sender = _mailer(_preferences("en-US"))

    await mailer.send_password_reset(_user(), TOKEN, EXPIRES_AT)

    assert f"{BASE_URL}/reset-password?token=" in sender.sent[0].body


async def test_an_account_with_no_name_is_greeted_by_its_address() -> None:
    mailer, sender = _mailer(_preferences("en-US"))

    await mailer.send_password_reset(_user(name=None), TOKEN, EXPIRES_AT)

    assert "reader@example.com" in sender.sent[0].body


async def test_the_mail_goes_to_the_address_on_file() -> None:
    mailer, sender = _mailer(_preferences("en-US"))

    await mailer.send_password_reset(_user(), TOKEN, EXPIRES_AT)

    assert sender.sent[0].to == "reader@example.com"
