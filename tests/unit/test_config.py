from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import PLACEHOLDER_SECRET_KEY, Settings

_DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/db"
_STRONG_SECRET = "s" * 32


def _build(secret_key: str, jwt_algorithm: str = "HS256") -> Settings:
    return Settings(
        database_url=_DATABASE_URL,
        test_database_url=_DATABASE_URL,
        secret_key=secret_key,
        jwt_algorithm=jwt_algorithm,  # type: ignore[arg-type]
    )


def test_accepts_a_strong_secret_and_supported_algorithm() -> None:
    settings = _build(_STRONG_SECRET)
    assert settings.secret_key == _STRONG_SECRET
    assert settings.jwt_algorithm == "HS256"


def test_rejects_secret_key_shorter_than_32_characters() -> None:
    with pytest.raises(ValidationError):
        _build("s" * 31)


def test_rejects_the_example_placeholder_secret_key() -> None:
    assert len(PLACEHOLDER_SECRET_KEY) >= 32

    with pytest.raises(ValidationError):
        _build(PLACEHOLDER_SECRET_KEY)


def test_rejects_unsupported_jwt_algorithm() -> None:
    with pytest.raises(ValidationError):
        _build(_STRONG_SECRET, jwt_algorithm="none")


def test_does_not_require_a_test_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)

    settings = Settings(database_url=_DATABASE_URL, secret_key=_STRONG_SECRET)

    assert settings.test_database_url is None


def test_rejects_a_body_limit_that_admits_nothing() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url=_DATABASE_URL,
            secret_key=_STRONG_SECRET,
            max_request_body_bytes=0,
        )
