from collections.abc import MutableMapping
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy import Engine

TRACE_ID = "trace_id"
SPAN_ID = "span_id"
INSTRUMENTED = "_is_instrumented_by_opentelemetry"


def add_trace_ids(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event_dict[TRACE_ID] = format(context.trace_id, "032x")
        event_dict[SPAN_ID] = format(context.span_id, "016x")
    return event_dict


def configure_tracing(
    *, service_name: str, otlp_endpoint: str | None = None
) -> TracerProvider:
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return current

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    if otlp_endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        )
    trace.set_tracer_provider(provider)
    return provider


def instrument_app(app: FastAPI, *, excluded_urls: str = "") -> None:
    if getattr(app, INSTRUMENTED, False):
        return
    FastAPIInstrumentor.instrument_app(app, excluded_urls=excluded_urls)


def instrument_engine(engine: Engine) -> None:
    SQLAlchemyInstrumentor().instrument(engine=engine)
