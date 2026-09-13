from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import NamedTuple

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mail.message import Mail

EMAIL = "mailed@example.com"
PASSWORD = "secret123"
NEW_PASSWORD = "another-secret"


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[Mail] = []

    async def send(self, mail: Mail) -> None:
        self.sent.append(mail)

    def token_in(self, index: int) -> str:
        body = self.sent[index].body
        marker = "?token="
        start = body.index(marker) + len(marker)
        return body[start:].split()[0]


@pytest_asyncio.fixture
async def mailbox(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[RecordingSender]:
    sender = RecordingSender()
    monkeypatch.setattr("app.api.deps.get_mail_sender", lambda: sender)
    yield sender


class Registered(NamedTuple):
    email: str
    mailbox: RecordingSender


@asynccontextmanager
async def _borrowed(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    yield session


@pytest_asyncio.fixture
async def registered(
    client: AsyncClient,
    db_session: AsyncSession,
    mailbox: RecordingSender,
    monkeypatch: pytest.MonkeyPatch,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> Registered:
    monkeypatch.setattr(
        "app.api.mail_tasks.get_session_factory",
        lambda: lambda: _borrowed(db_session),
    )
    await user_factory(email=EMAIL, password=PASSWORD)
    mailbox.sent.clear()
    return Registered(EMAIL, mailbox)


async def test_registering_sends_a_confirmation(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    response = await client.post(
        "/api/v1/users", json={"email": "fresh@example.com", "password": PASSWORD}
    )

    assert response.status_code == 201
    assert response.json()["email_verified_at"] is None
    assert [mail.to for mail in mailbox.sent] == ["fresh@example.com"]


async def test_following_the_confirmation_link_stamps_the_account(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    await client.post(
        "/api/v1/users", json={"email": "fresh@example.com", "password": PASSWORD}
    )

    confirmed = await client.post(
        "/api/v1/auth/email/verify", json={"token": mailbox.token_in(0)}
    )

    assert confirmed.status_code == 204
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "fresh@example.com", "password": PASSWORD},
    )
    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.json()["email_verified_at"] is not None


async def test_a_confirmation_token_nobody_issued_is_refused(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    response = await client.post(
        "/api/v1/auth/email/verify", json={"token": "invented"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalidToken"


async def test_asking_again_right_away_sends_nothing(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    await client.post(
        "/api/v1/users", json={"email": "fresh@example.com", "password": PASSWORD}
    )
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "fresh@example.com", "password": PASSWORD},
    )
    mailbox.sent.clear()

    response = await client.post(
        "/api/v1/auth/email/verify/resend",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert response.status_code == 202
    assert mailbox.sent == []


async def test_asking_again_after_the_cooldown_sends_another(
    client: AsyncClient, mailbox: RecordingSender, monkeypatch: pytest.MonkeyPatch
) -> None:
    await client.post(
        "/api/v1/users", json={"email": "fresh@example.com", "password": PASSWORD}
    )
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "fresh@example.com", "password": PASSWORD},
    )
    mailbox.sent.clear()
    monkeypatch.setenv("MAIL_RESEND_COOLDOWN_SECONDS", "0")
    get_settings.cache_clear()

    response = await client.post(
        "/api/v1/auth/email/verify/resend",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    get_settings.cache_clear()

    assert response.status_code == 202
    assert [mail.to for mail in mailbox.sent] == ["fresh@example.com"]


async def test_resending_a_confirmation_needs_a_token(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/email/verify/resend")

    assert response.status_code == 401


async def test_forgetting_a_password_answers_the_same_either_way(
    client: AsyncClient, registered: Registered
) -> None:
    known = await client.post(
        "/api/v1/auth/password/forgot", json={"email": registered.email}
    )
    unknown = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "nobody@example.com"}
    )

    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content == b""
    assert [mail.to for mail in registered.mailbox.sent] == [registered.email]


async def test_the_reset_link_sets_a_new_password(
    client: AsyncClient, registered: Registered
) -> None:
    await client.post("/api/v1/auth/password/forgot", json={"email": registered.email})

    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={
            "token": registered.mailbox.token_in(0),
            "new_password": NEW_PASSWORD,
        },
    )

    assert reset.status_code == 204
    stale = await client.post(
        "/api/v1/auth/login",
        data={"username": registered.email, "password": PASSWORD},
    )
    fresh = await client.post(
        "/api/v1/auth/login",
        data={"username": registered.email, "password": NEW_PASSWORD},
    )
    assert stale.status_code == 401
    assert fresh.status_code == 200


async def test_a_reset_link_cannot_be_followed_twice(
    client: AsyncClient, registered: Registered
) -> None:
    await client.post("/api/v1/auth/password/forgot", json={"email": registered.email})
    token = registered.mailbox.token_in(0)
    await client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": NEW_PASSWORD},
    )

    again = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": "third-secret"},
    )

    assert again.status_code == 401


async def test_a_short_password_is_refused_before_the_token_is_spent(
    client: AsyncClient, registered: Registered
) -> None:
    await client.post("/api/v1/auth/password/forgot", json={"email": registered.email})
    token = registered.mailbox.token_in(0)

    refused = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "short"}
    )

    assert refused.status_code == 422
    accepted = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert accepted.status_code == 204


async def test_asking_twice_in_a_row_sends_one_message(
    client: AsyncClient, registered: Registered
) -> None:
    for _ in range(2):
        await client.post(
            "/api/v1/auth/password/forgot", json={"email": registered.email}
        )

    assert len(registered.mailbox.sent) == 1
