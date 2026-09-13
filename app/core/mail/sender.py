import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

import structlog

from app.core.mail.message import Mail

logger = structlog.stdlib.get_logger("app.mail")

SMTP_TIMEOUT_SECONDS = 10


class MailSender(Protocol):
    async def send(self, mail: Mail) -> None: ...


class LoggingMailSender:
    def __init__(self, sender: str) -> None:
        self._sender = sender

    async def send(self, mail: Mail) -> None:
        logger.info(
            "mail",
            sender=self._sender,
            to=mail.to,
            subject=mail.subject,
            body=mail.body,
        )


class SmtpMailSender:
    def __init__(
        self,
        *,
        sender: str,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        use_starttls: bool = True,
        timeout: int = SMTP_TIMEOUT_SECONDS,
    ) -> None:
        self._sender = sender
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_starttls = use_starttls
        self._timeout = timeout

    async def send(self, mail: Mail) -> None:
        await asyncio.to_thread(self._deliver, mail)

    def _deliver(self, mail: Mail) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = mail.to
        message["Subject"] = mail.subject
        message.set_content(mail.body)
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
            if self._use_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self._username and self._password:
                smtp.login(self._username, self._password)
            smtp.send_message(message)
