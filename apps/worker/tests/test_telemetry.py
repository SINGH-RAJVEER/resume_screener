
import pytest

from worker.telemetry import record_job_outcome, setup_telemetry, telemetry_enabled


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


def test_job_metrics_record_without_provider() -> None:
    # With no SDK provider installed the instruments are no-ops; recording
    # must not raise so job processing never depends on telemetry.
    record_job_outcome("resume_processing", "completed", 1.5)
