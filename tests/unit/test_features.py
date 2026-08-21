import pytest

from app.core.config import get_settings
from app.core.features import Feature, enabled_features, is_enabled, parse_features


@pytest.fixture(autouse=True)
def fresh_settings() -> None:
    get_settings.cache_clear()


def test_names_are_split_and_trimmed() -> None:
    assert parse_features(" items , request-log ") == frozenset(
        {"items", "request-log"}
    )


def test_an_empty_list_enables_nothing() -> None:
    assert parse_features("") == frozenset()


def test_only_known_flags_are_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATURE_FLAGS", "items,not-a-feature")

    assert enabled_features() == frozenset({Feature.ITEMS})


def test_a_flag_left_out_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATURE_FLAGS", "items")

    assert is_enabled(Feature.ITEMS)
    assert not is_enabled(Feature.REQUEST_LOG)
