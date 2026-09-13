from datetime import datetime
from urllib.parse import quote

from app.core.i18n import locale as locales
from app.core.i18n import timezone as timezones
from app.core.mail.message import Mail
from app.core.mail.sender import MailSender
from app.core.mail.templates import RESET_PASSWORD, VERIFY_EMAIL, render
from app.models.user import User
from app.services.protocols import PreferencesRepositoryProtocol

MOMENT_FORMAT = "%Y-%m-%d %H:%M %Z"
VERIFY_PATH = "verify-email"
RESET_PATH = "reset-password"


class AccountMailer:
    def __init__(
        self,
        sender: MailSender,
        preferences: PreferencesRepositoryProtocol,
        *,
        base_url: str,
    ) -> None:
        self._sender = sender
        self._preferences = preferences
        self._base_url = base_url.rstrip("/")

    async def send_email_verification(
        self, user: User, token: str, expires_at: datetime
    ) -> None:
        await self._send(VERIFY_EMAIL, VERIFY_PATH, user, token, expires_at)

    async def send_password_reset(
        self, user: User, token: str, expires_at: datetime
    ) -> None:
        await self._send(RESET_PASSWORD, RESET_PATH, user, token, expires_at)

    async def _send(
        self,
        template: str,
        path: str,
        user: User,
        token: str,
        expires_at: datetime,
    ) -> None:
        stored = await self._preferences.get_for_user(user.id)
        locale = locales.resolve(None if stored is None else stored.locale)
        zone = timezones.resolve(None if stored is None else stored.timezone)
        rendered = render(
            template,
            locale,
            {
                "name": user.name or user.email,
                "link": f"{self._base_url}/{path}?token={quote(token, safe='')}",
                "expires_at": expires_at.astimezone(zone).strftime(MOMENT_FORMAT),
            },
        )
        await self._sender.send(Mail(user.email, rendered.subject, rendered.body))
