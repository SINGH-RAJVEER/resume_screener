from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerSettings:
	database_url: str
	storage_root: Path
	poll_interval_seconds: float
	lease_seconds: int


def load_settings() -> WorkerSettings:
	database_url = os.environ.get("DATABASE_URL", "")
	if not database_url:
		raise ValueError("DATABASE_URL environment variable is required")
	poll_interval = float(os.environ.get("WORKER_POLL_INTERVAL_SECONDS", "2"))
	lease_seconds = int(os.environ.get("WORKER_LEASE_SECONDS", "60"))
	if poll_interval <= 0 or lease_seconds <= 0:
		raise ValueError("Worker intervals must be positive")
	return WorkerSettings(
		database_url=database_url,
		storage_root=Path(os.environ.get("STORAGE_ROOT", ".local-storage")),
		poll_interval_seconds=poll_interval,
		lease_seconds=lease_seconds,
	)
