
import pytest

from app.telemetry import setup_telemetry, telemetry_enabled


def test_telemetry_disabled_without_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)

    assert telemetry_enabled() is False
    assert setup_telemetry() is False


def test_telemetry_respects_sdk_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    assert telemetry_enabled() is False
    assert setup_telemetry() is False


def test_telemetry_enables_tracing_with_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)

    assert setup_telemetry() is True
    try:
        assert isinstance(trace.get_tracer_provider(), TracerProvider)
        with trace.get_tracer("test").start_as_current_span("probe") as span:
            assert span.is_recording()
    finally:
        trace.get_tracer_provider().shutdown()  # type: ignore[attr-defined]
