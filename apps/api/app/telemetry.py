
# pyright: reportMissingTypeStubs=false

import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger("skillsignal.api")

SERVICE_NAME = "skillsignal-api"


def telemetry_enabled() -> bool:
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")) and os.environ.get(
        "OTEL_SDK_DISABLED", ""
    ).lower() != "true"


def setup_telemetry() -> bool:
    if not telemetry_enabled():
        return False
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry tracing enabled via OTEL_EXPORTER_OTLP_ENDPOINT")
    return True


def instrument_app(application: object) -> None:
    FastAPIInstrumentor.instrument_app(application)  # pyright: ignore[reportArgumentType]


def instrument_engine(engine: AsyncEngine) -> None:
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)  # pyright: ignore[reportCallIssue]
