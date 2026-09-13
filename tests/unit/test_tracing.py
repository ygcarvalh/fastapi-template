from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from app.core.observability.tracing import add_trace_ids, configure_tracing

SERVICE = "tracing-test"


def test_a_line_logged_outside_a_span_carries_no_trace() -> None:
    assert add_trace_ids(None, "info", {"event": "hello"}) == {"event": "hello"}


def test_a_line_logged_inside_a_span_carries_the_trace() -> None:
    provider = configure_tracing(service_name=SERVICE)

    with provider.get_tracer(SERVICE).start_as_current_span("work"):
        event = add_trace_ids(None, "info", {"event": "hello"})

    assert len(event["trace_id"]) == 32
    assert len(event["span_id"]) == 16


def test_configuring_twice_keeps_the_provider_already_installed() -> None:
    first = configure_tracing(service_name=SERVICE)
    second = configure_tracing(service_name=SERVICE)

    assert isinstance(first, TracerProvider)
    assert first is second
    assert trace.get_tracer_provider() is first
