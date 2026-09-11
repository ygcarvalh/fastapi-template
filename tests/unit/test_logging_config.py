import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from app.core.observability.logging import configure_logging
from app.core.observability.request_context import set_request_id


@pytest.fixture(autouse=True)
def restore_root_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    config = structlog.get_config()
    try:
        yield
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(level)
        structlog.configure(**config)
        set_request_id(None)


def _emit(message: str = "hello") -> None:
    logging.getLogger("app.example").info(message)


def test_json_output_carries_the_standard_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", json_format=True, service_name="probe")
    set_request_id(None)

    _emit()
    record = json.loads(capsys.readouterr().out.strip())

    assert record["event"] == "hello"
    assert record["level"] == "info"
    assert record["logger"] == "app.example"
    assert record["service"] == "probe"
    assert "timestamp" in record
    assert "request_id" not in record


def test_json_output_carries_the_current_request_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", json_format=True, service_name="probe")
    set_request_id("abc123")

    _emit()
    record = json.loads(capsys.readouterr().out.strip())

    assert record["request_id"] == "abc123"


def test_the_level_is_honored(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="WARNING", json_format=True, service_name="probe")

    _emit()

    assert capsys.readouterr().out == ""


def test_console_format_does_not_emit_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", json_format=False, service_name="probe")

    _emit()
    output = capsys.readouterr().out

    assert "hello" in output
    with pytest.raises(json.JSONDecodeError):
        json.loads(output.strip())


def test_a_traceback_reaches_the_json_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(level="INFO", json_format=True, service_name="probe")

    try:
        raise RuntimeError("the real cause")
    except RuntimeError as exc:
        logging.getLogger("app.example").error("boom", exc_info=exc)
    record = json.loads(capsys.readouterr().out.strip())

    assert "the real cause" in record["exception"]


def test_a_log_file_receives_json_alongside_stdout(tmp_path: Path) -> None:
    log_file = tmp_path / "nested" / "api.jsonl"
    configure_logging(
        level="INFO",
        json_format=False,
        service_name="probe",
        log_file=str(log_file),
    )

    _emit("written to disk")
    logging.shutdown()
    record = json.loads(log_file.read_text().strip())

    assert record["event"] == "written to disk"
