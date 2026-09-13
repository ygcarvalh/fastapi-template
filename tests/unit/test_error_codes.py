import re

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import (
    AuthError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
)

CODE_PATTERN = r"^[a-z][a-zA-Z]*\.[a-z][a-zA-Z]*$"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (DomainError("boom"), ErrorCode.UNEXPECTED),
        (NotFoundError("gone"), ErrorCode.NOT_FOUND),
        (ConflictError("taken"), ErrorCode.CONFLICT),
        (AuthError("nope"), ErrorCode.UNAUTHORIZED),
        (ForbiddenError("nope"), ErrorCode.FORBIDDEN),
        (PayloadTooLargeError("big"), ErrorCode.PAYLOAD_TOO_LARGE),
    ],
)
def test_every_domain_error_carries_a_code(
    error: DomainError, expected: ErrorCode
) -> None:
    assert error.code == expected


def test_a_raise_site_can_name_a_more_precise_code() -> None:
    error = NotFoundError("Item not found", code=ErrorCode.ITEM_NOT_FOUND)

    assert error.code == ErrorCode.ITEM_NOT_FOUND
    assert error.status_code == 404


def test_params_travel_with_the_code_for_interpolation() -> None:
    error = ConflictError("Too many", params={"limit": 5})

    assert error.params == {"limit": 5}


def test_a_raise_site_leaves_params_empty_by_default() -> None:
    assert DomainError("boom").params == {}


def test_codes_are_namespaced_and_camel_cased() -> None:
    for code in ErrorCode:
        assert re.match(CODE_PATTERN, code.value), code.value


def test_codes_are_unique() -> None:
    values = [code.value for code in ErrorCode]

    assert len(values) == len(set(values))
