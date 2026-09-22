import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, NamedTuple
from uuid import uuid4

import anyio.to_thread
import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import get_settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AuthError

password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))

TokenType = Literal["access", "refresh"]

ACCESS_TOKEN_TYPE: TokenType = "access"  # noqa: S105
REFRESH_TOKEN_TYPE: TokenType = "refresh"  # noqa: S105

INVALID_CREDENTIALS = "Invalid authentication credentials"


def invalid_credentials() -> AuthError:
    return AuthError(INVALID_CREDENTIALS, code=ErrorCode.AUTH_INVALID_CREDENTIALS)


IMPERSONATOR_CLAIM = "act"

SINGLE_USE_TOKEN_BYTES = 32


class AccessClaims(NamedTuple):
    subject: str
    impersonator: str | None
    issued_at: datetime


async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(password_hash.hash, password)


async def verify_password(password: str, hashed: str) -> bool:
    return await anyio.to_thread.run_sync(password_hash.verify, password, hashed)


# A digest, not a password hash: the token is already high-entropy, and the
# lookup that checks it has to be deterministic.
def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_single_use_token() -> str:
    return secrets.token_urlsafe(SINGLE_USE_TOKEN_BYTES)


def hash_single_use_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create_token(
    subject: str,
    token_type: TokenType,
    lifetime: timedelta,
    impersonator: str | None = None,
) -> str:
    settings = get_settings()
    issued_at = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "jti": uuid4().hex,
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }
    if impersonator is not None:
        payload[IMPERSONATOR_CLAIM] = {"sub": impersonator}
    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(subject: str) -> str:
    settings = get_settings()
    return _create_token(
        subject,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: str) -> str:
    settings = get_settings()
    return _create_token(
        subject,
        REFRESH_TOKEN_TYPE,
        timedelta(days=settings.refresh_token_expire_days),
    )


def create_impersonation_token(subject: str, impersonator: str) -> str:
    settings = get_settings()
    return _create_token(
        subject,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.impersonation_token_expire_minutes),
        impersonator=impersonator,
    )


def _decode(token: str, expected_type: TokenType) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise invalid_credentials() from exc

    if payload.get("typ") != expected_type:
        raise invalid_credentials()

    if payload.get("sub") is None:
        raise invalid_credentials()
    return payload


def _issued_at(payload: dict[str, Any]) -> datetime:
    issued = payload.get("iat")
    if not isinstance(issued, int):
        raise invalid_credentials()
    return datetime.fromtimestamp(issued, UTC)


def _impersonator_of(payload: dict[str, Any]) -> str | None:
    actor = payload.get(IMPERSONATOR_CLAIM)
    if actor is None:
        return None
    if not isinstance(actor, dict) or actor.get("sub") is None:
        raise invalid_credentials()
    return str(actor["sub"])


def decode_access_token(token: str) -> AccessClaims:
    payload = _decode(token, ACCESS_TOKEN_TYPE)
    return AccessClaims(
        str(payload["sub"]), _impersonator_of(payload), _issued_at(payload)
    )


def decode_refresh_token(token: str) -> str:
    payload = _decode(token, REFRESH_TOKEN_TYPE)
    if payload.get(IMPERSONATOR_CLAIM) is not None:
        raise invalid_credentials()
    return str(payload["sub"])
