import logging

import pytest

from app.core.mail.message import Mail
from app.core.mail.sender import LoggingMailSender

MAIL = Mail(to="reader@example.com", subject="Hello", body="A link lives here")


async def test_the_development_sender_writes_the_whole_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        await LoggingMailSender("no-reply@example.com").send(MAIL)

    assert "reader@example.com" in caplog.text
    assert "A link lives here" in caplog.text
