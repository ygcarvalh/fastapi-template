from datetime import UTC, datetime

import pytest

from app.core.i18n.timezone import DEFAULT_TIMEZONE, is_known, resolve


@pytest.mark.parametrize("name", ["UTC", "America/Sao_Paulo", "Europe/Lisbon"])
def test_a_real_zone_is_known(name: str) -> None:
    assert is_known(name)


@pytest.mark.parametrize("name", ["", "Mars/Olympus", "America/Sao Paulo", "-03:00"])
def test_anything_that_is_not_an_iana_zone_is_refused(name: str) -> None:
    assert not is_known(name)


def test_a_stored_zone_shifts_the_moment_it_renders() -> None:
    moment = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    assert moment.astimezone(resolve("America/Sao_Paulo")).hour == 9


def test_a_zone_this_machine_never_heard_of_falls_back() -> None:
    assert str(resolve("Mars/Olympus")) == DEFAULT_TIMEZONE


def test_an_account_that_saved_no_zone_falls_back() -> None:
    assert str(resolve(None)) == DEFAULT_TIMEZONE
