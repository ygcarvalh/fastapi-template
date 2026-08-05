from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import AuthError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)


def _token_with(payload: dict[str, object]) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def test_refresh_token_round_trips() -> None:
    assert decode_refresh_token(create_refresh_token("42")) == "42"


def test_access_token_is_rejected_where_a_refresh_token_is_required() -> None:
    with pytest.raises(AuthError):
        decode_refresh_token(create_access_token("42"))


def test_refresh_token_is_rejected_where_an_access_token_is_required() -> None:
    with pytest.raises(AuthError):
        decode_access_token(create_refresh_token("42"))


def test_token_without_a_type_claim_is_rejected() -> None:
    legacy = _token_with(
        {"sub": "42", "exp": datetime.now(UTC) + timedelta(minutes=5)},
    )

    with pytest.raises(AuthError):
        decode_access_token(legacy)


def test_expired_refresh_token_is_rejected() -> None:
    expired = _token_with(
        {
            "sub": "42",
            "typ": "refresh",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        }
    )

    with pytest.raises(AuthError):
        decode_refresh_token(expired)


def test_refresh_token_without_a_subject_is_rejected() -> None:
    subjectless = _token_with(
        {"typ": "refresh", "exp": datetime.now(UTC) + timedelta(days=1)}
    )

    with pytest.raises(AuthError):
        decode_refresh_token(subjectless)


def test_refresh_tokens_outlive_access_tokens() -> None:
    settings = get_settings()
    access = jwt.decode(
        create_access_token("42"),
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    refresh = jwt.decode(
        create_refresh_token("42"),
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert refresh["exp"] > access["exp"]
