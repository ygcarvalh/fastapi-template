from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

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


async def test_registering_sends_a_confirmation(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    response = await client.post(
        "/api/v1/users", json={"email": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 201
    assert response.json()["email_verified_at"] is None
    assert [mail.to for mail in mailbox.sent] == [EMAIL]


async def test_following_the_confirmation_link_stamps_the_account(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    await client.post("/api/v1/users", json={"email": EMAIL, "password": PASSWORD})

    confirmed = await client.post(
        "/api/v1/auth/email/verify", json={"token": mailbox.token_in(0)}
    )

    assert confirmed.status_code == 204
    login = await client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD}
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


async def test_forgetting_a_password_answers_the_same_either_way(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    await client.post("/api/v1/users", json={"email": EMAIL, "password": PASSWORD})
    mailbox.sent.clear()

    known = await client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    unknown = await client.post(
        "/api/v1/auth/password/forgot", json={"email": "nobody@example.com"}
    )

    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content == b""
    assert [mail.to for mail in mailbox.sent] == [EMAIL]


async def test_the_reset_link_sets_a_new_password(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    await client.post("/api/v1/users", json={"email": EMAIL, "password": PASSWORD})
    mailbox.sent.clear()
    await client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})

    reset = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": mailbox.token_in(0), "new_password": NEW_PASSWORD},
    )

    assert reset.status_code == 204
    stale = await client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD}
    )
    fresh = await client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": NEW_PASSWORD}
    )
    assert stale.status_code == 401
    assert fresh.status_code == 200


async def test_a_reset_signs_the_sessions_already_open_out(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    await client.post("/api/v1/users", json={"email": EMAIL, "password": PASSWORD})
    login = await client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD}
    )
    refresh_token = login.json()["refresh_token"]
    mailbox.sent.clear()
    await client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    await client.post(
        "/api/v1/auth/password/reset",
        json={"token": mailbox.token_in(0), "new_password": NEW_PASSWORD},
    )

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )

    assert refreshed.status_code == 401


async def test_a_reset_link_cannot_be_followed_twice(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    await client.post("/api/v1/users", json={"email": EMAIL, "password": PASSWORD})
    mailbox.sent.clear()
    await client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    token = mailbox.token_in(0)
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
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    await client.post("/api/v1/users", json={"email": EMAIL, "password": PASSWORD})
    mailbox.sent.clear()
    await client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    token = mailbox.token_in(0)

    refused = await client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "short"}
    )

    assert refused.status_code == 422
    accepted = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert accepted.status_code == 204


async def test_resending_a_confirmation_needs_a_token(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/email/verify/resend")

    assert response.status_code == 401


async def test_an_account_can_ask_for_the_confirmation_again(
    client: AsyncClient, mailbox: RecordingSender
) -> None:
    await client.post("/api/v1/users", json={"email": EMAIL, "password": PASSWORD})
    login = await client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD}
    )
    mailbox.sent.clear()

    response = await client.post(
        "/api/v1/auth/email/verify/resend",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert response.status_code == 202
    assert [mail.to for mail in mailbox.sent] == [EMAIL]
