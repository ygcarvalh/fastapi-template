from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import PLACEHOLDER_SECRET_KEY, Settings

_DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/db"
_STRONG_SECRET = "s" * 32
_STRONG_SECRET_KEY = SecretStr(_STRONG_SECRET)


def _build(secret_key: str, jwt_algorithm: str = "HS256") -> Settings:
    return Settings(
        database_url=_DATABASE_URL,
        test_database_url=_DATABASE_URL,
        secret_key=SecretStr(secret_key),
        jwt_algorithm=jwt_algorithm,  # type: ignore[arg-type]
    )


def test_accepts_a_strong_secret_and_supported_algorithm() -> None:
    settings = _build(_STRONG_SECRET)
    assert settings.secret_key.get_secret_value() == _STRONG_SECRET
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

    settings = Settings(database_url=_DATABASE_URL, secret_key=_STRONG_SECRET_KEY)

    assert settings.test_database_url is None


def test_rejects_a_body_limit_that_admits_nothing() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url=_DATABASE_URL,
            secret_key=_STRONG_SECRET_KEY,
            max_request_body_bytes=0,
        )


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(
        database_url=_DATABASE_URL,
        secret_key=_STRONG_SECRET_KEY,
        cors_origins=" https://a.example.com, https://b.example.com ,",
    )

    assert settings.cors_origin_list == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_cors_origins_default_to_none() -> None:
    settings = Settings(database_url=_DATABASE_URL, secret_key=_STRONG_SECRET_KEY)

    assert settings.cors_origin_list == []


def test_a_wildcard_cors_origin_is_refused() -> None:
    with pytest.raises(ValidationError, match="named origins"):
        Settings(
            database_url=_DATABASE_URL,
            secret_key=_STRONG_SECRET_KEY,
            cors_origins="https://a.example.com, *",
        )


def test_an_upload_ceiling_above_the_body_limit_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "1048576")
    monkeypatch.setenv("MAX_ATTACHMENT_BYTES", "5242880")

    with pytest.raises(ValidationError) as raised:
        Settings()  # type: ignore[call-arg]

    assert "MAX_REQUEST_BODY_BYTES" in str(raised.value)


def test_an_upload_ceiling_under_the_body_limit_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "8388608")
    monkeypatch.setenv("MAX_ATTACHMENT_BYTES", "5242880")

    assert Settings().max_attachment_bytes == 5242880  # type: ignore[call-arg]


def test_secret_key_is_wrapped_in_secret_str() -> None:
    settings = _build(_STRONG_SECRET)

    assert str(settings.secret_key) == "**********"
    assert settings.secret_key.get_secret_value() == _STRONG_SECRET


def test_docs_default_on_outside_production() -> None:
    settings = Settings(
        database_url=_DATABASE_URL,
        secret_key=_STRONG_SECRET_KEY,
        environment="staging",
        docs_enabled=None,
    )

    assert settings.docs_are_enabled is True


def test_docs_default_off_in_production() -> None:
    settings = Settings(
        database_url=_DATABASE_URL,
        secret_key=_STRONG_SECRET_KEY,
        environment="production",
        docs_enabled=None,
    )

    assert settings.docs_are_enabled is False


def test_docs_enabled_explicitly_overrides_the_environment_default() -> None:
    settings = Settings(
        database_url=_DATABASE_URL,
        secret_key=_STRONG_SECRET_KEY,
        environment="production",
        docs_enabled=True,
    )

    assert settings.docs_are_enabled is True


def test_hsts_default_off_outside_production() -> None:
    settings = Settings(
        database_url=_DATABASE_URL,
        secret_key=_STRONG_SECRET_KEY,
        environment="staging",
        hsts_enabled=None,
    )

    assert settings.hsts_is_enabled is False


def test_hsts_default_on_in_production() -> None:
    settings = Settings(
        database_url=_DATABASE_URL,
        secret_key=_STRONG_SECRET_KEY,
        environment="production",
        hsts_enabled=None,
    )

    assert settings.hsts_is_enabled is True


def test_hsts_enabled_explicitly_overrides_the_environment_default() -> None:
    settings = Settings(
        database_url=_DATABASE_URL,
        secret_key=_STRONG_SECRET_KEY,
        environment="development",
        hsts_enabled=True,
    )

    assert settings.hsts_is_enabled is True


def test_rejects_an_unsupported_environment() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url=_DATABASE_URL,
            secret_key=_STRONG_SECRET_KEY,
            environment="prod",  # type: ignore[arg-type]
        )
