import logging

from app.core.observability.request_context import (
    MAX_REQUEST_ID_LENGTH,
    add_request_id,
    get_request_id,
    new_request_id,
    sanitize_request_id,
    set_request_id,
)


def test_a_minted_id_is_hex_and_survives_sanitizing() -> None:
    minted = new_request_id()

    assert sanitize_request_id(minted) == minted


def test_a_wellformed_inbound_id_is_accepted() -> None:
    assert sanitize_request_id("abc-123_XYZ") == "abc-123_XYZ"


def test_a_missing_id_is_rejected() -> None:
    assert sanitize_request_id(None) is None


def test_an_empty_id_is_rejected() -> None:
    assert sanitize_request_id("") is None


def test_an_id_carrying_a_newline_is_rejected() -> None:
    assert sanitize_request_id("clean\ninjected") is None


def test_an_overlong_id_is_rejected() -> None:
    assert sanitize_request_id("a" * (MAX_REQUEST_ID_LENGTH + 1)) is None


def test_an_id_at_the_length_limit_is_accepted() -> None:
    value = "a" * MAX_REQUEST_ID_LENGTH

    assert sanitize_request_id(value) == value


def test_the_processor_adds_the_current_id() -> None:
    set_request_id("abc123")

    assert add_request_id(logging, "info", {}) == {"request_id": "abc123"}
    assert get_request_id() == "abc123"


def test_the_processor_leaves_the_event_alone_without_an_id() -> None:
    set_request_id(None)

    assert add_request_id(logging, "info", {"event": "x"}) == {"event": "x"}
    assert get_request_id() is None
