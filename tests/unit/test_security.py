from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import AuthError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_access_token_round_trip() -> None:
    token = create_access_token("42")
    assert decode_access_token(token) == "42"


def test_decode_invalid_token_raises() -> None:
    with pytest.raises(AuthError):
        decode_access_token("not-a-valid-token")


def test_decode_token_without_a_subject_raises() -> None:
    settings = get_settings()
    token = jwt.encode(
        {"exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(AuthError):
        decode_access_token(token)


def test_decode_expired_token_raises() -> None:
    settings = get_settings()
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(AuthError):
        decode_access_token(token)


def test_decode_token_signed_with_another_key_raises() -> None:
    settings = get_settings()
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "a" * 32,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(AuthError):
        decode_access_token(token)
