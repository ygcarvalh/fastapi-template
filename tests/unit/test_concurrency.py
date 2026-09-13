import pytest

from app.core.exceptions import PreconditionFailedError, PreconditionRequiredError
from app.core.http.concurrency import etag_for, parse_etag, require_if_match


def test_an_etag_is_weak_and_carries_the_version() -> None:
    assert etag_for(7) == 'W/"7"'


@pytest.mark.parametrize("value", ['W/"3"', '"3"', "3", '  W/"3" '])
def test_every_shape_a_client_sends_back_reads_the_same(value: str) -> None:
    assert parse_etag(value) == 3


@pytest.mark.parametrize("value", ["", "abc", 'W/""', "3.5"])
def test_an_etag_this_api_never_issued_reads_as_nothing(value: str) -> None:
    assert parse_etag(value) is None


async def test_a_missing_header_asks_for_one() -> None:
    with pytest.raises(PreconditionRequiredError) as raised:
        await require_if_match(None)

    assert raised.value.status_code == 428


async def test_a_star_means_no_version_to_check() -> None:
    assert await require_if_match("*") is None


async def test_a_malformed_header_fails_the_precondition() -> None:
    with pytest.raises(PreconditionFailedError) as raised:
        await require_if_match("nonsense")

    assert raised.value.status_code == 412
