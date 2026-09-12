import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, NamedTuple
from uuid import uuid4

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import get_settings
from app.core.exceptions import AuthError

password_hash = PasswordHash((BcryptHasher(),))

TokenType = Literal["access", "refresh"]

ACCESS_TOKEN_TYPE: TokenType = "access"
REFRESH_TOKEN_TYPE: TokenType = "refresh"

INVALID_CREDENTIALS = "Invalid authentication credentials"

IMPERSONATOR_CLAIM = "act"


class AccessClaims(NamedTuple):
    subject: str
    impersonator: str | None


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


# A digest, not a password hash: the token is already high-entropy, and the
# lookup that checks it has to be deterministic.
def hash_refresh_token(token: str) -> str:
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
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


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


# A token carrying an impersonation lifetime of its own, and no refresh token
# to renew it with: leaving as somebody else is a matter of dropping it.
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
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise AuthError(INVALID_CREDENTIALS) from exc

    if payload.get("typ") != expected_type:
        raise AuthError(INVALID_CREDENTIALS)

    if payload.get("sub") is None:
        raise AuthError(INVALID_CREDENTIALS)
    return payload


def _impersonator_of(payload: dict[str, Any]) -> str | None:
    actor = payload.get(IMPERSONATOR_CLAIM)
    if actor is None:
        return None
    if not isinstance(actor, dict) or actor.get("sub") is None:
        raise AuthError(INVALID_CREDENTIALS)
    return str(actor["sub"])


def decode_access_token(token: str) -> AccessClaims:
    payload = _decode(token, ACCESS_TOKEN_TYPE)
    return AccessClaims(str(payload["sub"]), _impersonator_of(payload))


# An impersonation token must never buy a session of its own, so a refresh
# token carrying the claim is refused rather than quietly honoured.
def decode_refresh_token(token: str) -> str:
    payload = _decode(token, REFRESH_TOKEN_TYPE)
    if payload.get(IMPERSONATOR_CLAIM) is not None:
        raise AuthError(INVALID_CREDENTIALS)
    return str(payload["sub"])
