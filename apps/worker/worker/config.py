
import os
from dataclasses import dataclass
from pathlib import Path

from .billing import BillingSettings


@dataclass(frozen=True)
class OpenRouterSettings:
	api_key: str | None
	base_url: str
	extraction_model: str
	assessment_model: str
	embedding_model: str
	timeout_seconds: float
	max_output_tokens: int


@dataclass(frozen=True)
class WorkerSettings:
	database_url: str
	storage_root: Path
	poll_interval_seconds: float
	lease_seconds: int
	parse_timeout_seconds: float
	openrouter: OpenRouterSettings
	billing: BillingSettings = BillingSettings()

	@property
	def llm_enabled(self) -> bool:
		return self.openrouter.api_key is not None


def load_settings() -> WorkerSettings:
	database_url = os.environ.get("DATABASE_URL", "")
	if not database_url:
		raise ValueError("DATABASE_URL environment variable is required")
	poll_interval = float(os.environ.get("WORKER_POLL_INTERVAL_SECONDS", "2"))
	lease_seconds = int(os.environ.get("WORKER_LEASE_SECONDS", "60"))
	parse_timeout = float(os.environ.get("PARSE_TIMEOUT_SECONDS", "30"))
	if poll_interval <= 0 or lease_seconds <= 0 or parse_timeout <= 0:
		raise ValueError("Worker intervals and timeouts must be positive")
	openrouter = OpenRouterSettings(
		api_key=os.environ.get("OPENROUTER_API_KEY") or None,
		base_url=os.environ.get("OPENROUTER_BASE_URL", "")
		or "https://openrouter.ai/api/v1",
		extraction_model=os.environ.get("OPENROUTER_EXTRACTION_MODEL", "")
		or "openai/gpt-5-mini",
		assessment_model=os.environ.get("OPENROUTER_ASSESSMENT_MODEL", "")
		or "openai/gpt-5-mini",
		embedding_model=os.environ.get("OPENROUTER_EMBEDDING_MODEL", "")
		or "qwen/qwen3-embedding-8b",
		timeout_seconds=float(os.environ.get("OPENROUTER_TIMEOUT_SECONDS") or "90"),
		max_output_tokens=int(os.environ.get("OPENROUTER_MAX_OUTPUT_TOKENS") or "4096"),
	)
	return WorkerSettings(
		database_url=database_url,
		storage_root=Path(os.environ.get("STORAGE_ROOT", ".local-storage")),
		poll_interval_seconds=poll_interval,
		lease_seconds=lease_seconds,
		parse_timeout_seconds=parse_timeout,
		openrouter=openrouter,
		billing=BillingSettings(
			points_per_usd=int(os.environ.get("POINTS_PER_USD") or "1000"),
			minimum_independent_evaluation_points=int(
				os.environ.get("MIN_POINTS_INDEPENDENT_EVALUATION") or "10"
			),
			minimum_employer_resume_points=int(
				os.environ.get("MIN_POINTS_EMPLOYER_RESUME") or "5"
			),
			price_ceiling_usd_per_million_input=float(
				os.environ.get("PRICE_CEILING_INPUT_USD_PER_MILLION") or "3.0"
			),
			price_ceiling_usd_per_million_output=float(
				os.environ.get("PRICE_CEILING_OUTPUT_USD_PER_MILLION") or "15.0"
			),
		),
	)
