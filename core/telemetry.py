"""OpenTelemetry tracing foundation."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

_tracer: trace.Tracer | None = None
_initialized = False


def init_telemetry(service_name: str = "aws-docs-api") -> None:
    """Configure the global tracer provider (idempotent)."""
    global _tracer, _initialized
    if _initialized:
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        except Exception:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    _initialized = True


def get_tracer() -> trace.Tracer:
    if _tracer is None:
        init_telemetry()
    return _tracer or trace.get_tracer("aws-docs-api")


def instrument_fastapi(app: Any) -> None:
    """Attach FastAPI auto-instrumentation when the optional package is available."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Generator[None, None, None]:
    """Context manager for a traced operation."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        yield
