from datetime import UTC, datetime, timedelta
from typing import Literal

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


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def _create_token(subject: str, token_type: TokenType, lifetime: timedelta) -> str:
    settings = get_settings()
    issued_at = datetime.now(UTC)
    payload = {
        "sub": subject,
        "typ": token_type,
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }
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


def _decode(token: str, expected_type: TokenType) -> str:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise AuthError(INVALID_CREDENTIALS) from exc

    if payload.get("typ") != expected_type:
        raise AuthError(INVALID_CREDENTIALS)

    subject = payload.get("sub")
    if subject is None:
        raise AuthError(INVALID_CREDENTIALS)
    return str(subject)


def decode_access_token(token: str) -> str:
    return _decode(token, ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> str:
    return _decode(token, REFRESH_TOKEN_TYPE)
