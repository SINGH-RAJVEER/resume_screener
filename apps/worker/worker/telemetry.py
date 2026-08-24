
# pyright: reportMissingTypeStubs=false

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.metrics import Counter, Histogram
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("skillsignal.worker")

SERVICE_NAME = "skillsignal-worker"


def telemetry_enabled() -> bool:
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")) and os.environ.get(
        "OTEL_SDK_DISABLED", ""
    ).lower() != "true"


def setup_telemetry() -> bool:
    if not telemetry_enabled():
        return False
    resource = Resource.create({"service.name": SERVICE_NAME})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(meter_provider)
    logger.info("OpenTelemetry tracing and metrics enabled via OTEL_EXPORTER_OTLP_ENDPOINT")
    return True


# Acquired against the global proxy providers so they resolve once
# setup_telemetry installs the SDK providers, and stay no-op otherwise.
tracer: Tracer = trace.get_tracer(SERVICE_NAME)
_jobs_counter: Counter = metrics.get_meter(SERVICE_NAME).create_counter(
    "skillsignal.worker.jobs",
    unit="{job}",
    description="Processing jobs finished by the worker, by type and outcome.",
)
_job_duration: Histogram = metrics.get_meter(SERVICE_NAME).create_histogram(
    "skillsignal.worker.job_duration",
    unit="s",
    description="Wall-clock time to process a claimed job.",
)


def record_job_outcome(job_type: str, outcome: str, duration_seconds: float) -> None:
    _jobs_counter.add(1, {"job.type": job_type, "outcome": outcome})
    _job_duration.record(duration_seconds, {"job.type": job_type})


def instrument_engine(engine: AsyncEngine) -> None:
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)  # pyright: ignore[reportCallIssue]


def instrument_httpx_clients() -> None:
    # Covers the OpenRouter client; request bodies carry resume content and
    # are never captured, only method, URL, status, and timing.
    HTTPXClientInstrumentor.instrument()  # pyright: ignore[reportCallIssue]


def shutdown_telemetry() -> None:
    for provider in (trace.get_tracer_provider(), metrics.get_meter_provider()):
        shutdown = getattr(provider, "shutdown", None)
        if shutdown is not None:
            shutdown()
