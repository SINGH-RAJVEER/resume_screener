import pytest

from worker.config import load_settings


def test_load_settings_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.delenv("DATABASE_URL", raising=False)

	with pytest.raises(ValueError, match="DATABASE_URL"):
		load_settings()


def test_load_settings_reads_worker_limits(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://worker:secret@db/resume_screener")
	monkeypatch.setenv("WORKER_POLL_INTERVAL_SECONDS", "1.5")
	monkeypatch.setenv("WORKER_LEASE_SECONDS", "45")

	settings = load_settings()

	assert settings.poll_interval_seconds == 1.5
	assert settings.lease_seconds == 45
