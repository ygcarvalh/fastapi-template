import pytest

from app.core.config import get_settings
from app.core.features import (
    Feature,
    enabled_features,
    inherited_features,
    is_enabled,
    parse_features,
)


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


def test_a_role_without_a_list_hands_down_nothing() -> None:
    assert inherited_features([None, None], enabled_features()) is None


def test_the_lists_of_every_role_add_up() -> None:
    ceiling = frozenset({Feature.ITEMS, Feature.REQUEST_LOG})

    inherited = inherited_features(["items", "request-log"], ceiling)

    assert inherited == ceiling


def test_a_role_list_cannot_reach_past_what_the_deployment_serves() -> None:
    ceiling = frozenset({Feature.ITEMS})

    inherited = inherited_features(["items,request-log"], ceiling)

    assert inherited == frozenset({Feature.ITEMS})


def test_a_role_that_turns_everything_off_is_a_real_answer() -> None:
    ceiling = frozenset({Feature.ITEMS})

    assert inherited_features([""], ceiling) == frozenset()
