import pytest

from app.core.i18n.locale import (
    DEFAULT_LOCALE,
    Locale,
    coerce,
    negotiate,
    ranked_tags,
    resolve,
)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("pt-BR", Locale.PT_BR),
        ("PT-br", Locale.PT_BR),
        ("  pt-BR  ", Locale.PT_BR),
        ("pt", Locale.PT_BR),
        ("pt-PT", Locale.PT_BR),
        ("en", Locale.EN_US),
        ("en-GB", Locale.EN_US),
    ],
)
def test_a_tag_this_service_speaks_is_recognized(tag: str, expected: Locale) -> None:
    assert coerce(tag) == expected


@pytest.mark.parametrize("tag", [None, "", "   ", "de", "*", "nonsense"])
def test_a_tag_this_service_does_not_speak_is_nothing(tag: str | None) -> None:
    assert coerce(tag) is None


def test_accept_language_is_read_in_the_order_the_caller_ranked_it() -> None:
    assert ranked_tags("de;q=0.5, pt-BR;q=0.9, en;q=0.8") == ["pt-BR", "en", "de"]


def test_a_tag_with_no_quality_outranks_one_that_named_a_lower_quality() -> None:
    assert ranked_tags("de, pt-BR;q=0.9") == ["de", "pt-BR"]


def test_a_tag_refused_by_the_caller_is_dropped() -> None:
    assert ranked_tags("de;q=0, pt-BR") == ["pt-BR"]


def test_negotiation_skips_languages_this_service_does_not_speak() -> None:
    assert negotiate("de, fr;q=0.9, pt-BR;q=0.1") == Locale.PT_BR


def test_negotiation_of_nothing_this_service_speaks_is_nothing() -> None:
    assert negotiate("de, fr") is None


def test_what_the_account_saved_outranks_what_the_request_asked_for() -> None:
    assert resolve("pt-BR", "en-US") == Locale.PT_BR


def test_a_request_header_answers_for_an_account_that_saved_nothing() -> None:
    assert resolve(None, "pt-BR,en;q=0.5") == Locale.PT_BR


def test_a_stored_tag_this_service_dropped_falls_back_to_the_request() -> None:
    assert resolve("de-DE", "pt-BR") == Locale.PT_BR


def test_with_nothing_to_go_on_the_deployment_default_answers() -> None:
    assert resolve(None, None) == DEFAULT_LOCALE
