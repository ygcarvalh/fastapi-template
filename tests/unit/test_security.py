import pytest

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
