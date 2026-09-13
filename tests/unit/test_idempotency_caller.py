from fastapi import Request

from app.api.idempotency_store import caller_of
from app.core.security import create_access_token, create_refresh_token


def _request(authorization: str | None) -> Request:
    headers = (
        [] if authorization is None else [(b"authorization", authorization.encode())]
    )
    return Request({"type": "http", "method": "POST", "headers": headers})


def test_a_valid_bearer_names_the_account_that_reserved_the_key() -> None:
    assert caller_of(_request(f"Bearer {create_access_token('12')}")) == 12


def test_a_lowercase_scheme_is_read_the_same_way() -> None:
    assert caller_of(_request(f"bearer {create_access_token('12')}")) == 12


def test_no_authorization_header_means_no_caller() -> None:
    assert caller_of(_request(None)) is None


def test_another_scheme_means_no_caller() -> None:
    assert caller_of(_request("Basic abc")) is None


def test_a_forged_token_means_no_caller() -> None:
    assert caller_of(_request("Bearer not-a-token")) is None


def test_a_refresh_token_cannot_reserve_a_key() -> None:
    assert caller_of(_request(f"Bearer {create_refresh_token('12')}")) is None
