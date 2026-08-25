import json
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RazorpayPack:
	id: str
	points: int
	amount_inr: int


@dataclass(frozen=True)
class TaskBudget:
	task: str
	max_input_tokens: int
	max_output_tokens: int


def _default_packs() -> tuple[RazorpayPack, ...]:
	return (
		RazorpayPack("pack-500", 500, 499),
		RazorpayPack("pack-2000", 2000, 1499),
	)


@dataclass(frozen=True)
class BillingSettings:
	"""Deployment-configured point economics and Razorpay credentials.

	Points are quoted from maximum token budgets and model price ceilings
	before an evaluation starts, so no usage can exceed the reserved amount.
	"""

	points_per_usd: int = 1000
	minimum_independent_evaluation_points: int = 10
	minimum_employer_resume_points: int = 5
	price_ceiling_usd_per_million_input: float = 3.0
	price_ceiling_usd_per_million_output: float = 15.0
	independent_budgets: tuple[TaskBudget, ...] = (
		TaskBudget("extraction", 16_000, 4_096),
	)
	employer_budgets: tuple[TaskBudget, ...] = (
		TaskBudget("extraction", 16_000, 4_096),
		TaskBudget("assessment", 24_000, 4_096),
		TaskBudget("embedding", 32_000, 0),
	)
	packs: tuple[RazorpayPack, ...] = field(default_factory=_default_packs)
	razorpay_key_id: str = ""
	razorpay_key_secret: str = ""
	razorpay_webhook_secret: str = ""
	admin_token: str = ""
	enterprise_sales_email: str = "sales@skillsignal.app"

	def pack(self, pack_id: str) -> RazorpayPack | None:
		for pack in self.packs:
			if pack.id == pack_id:
				return pack
		return None

	@property
	def razorpay_configured(self) -> bool:
		return bool(self.razorpay_key_id and self.razorpay_key_secret)

	@property
	def webhook_verification_enabled(self) -> bool:
		return bool(self.razorpay_webhook_secret)


def load_billing_settings() -> BillingSettings:
	return BillingSettings(
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
		independent_budgets=(
			TaskBudget(
				"extraction",
				int(os.environ.get("QUOTE_EXTRACTION_INPUT_TOKENS") or "16000"),
				int(os.environ.get("QUOTE_EXTRACTION_OUTPUT_TOKENS") or "4096"),
			),
		),
		employer_budgets=(
			TaskBudget(
				"extraction",
				int(os.environ.get("QUOTE_EXTRACTION_INPUT_TOKENS") or "16000"),
				int(os.environ.get("QUOTE_EXTRACTION_OUTPUT_TOKENS") or "4096"),
			),
			TaskBudget(
				"assessment",
				int(os.environ.get("QUOTE_ASSESSMENT_INPUT_TOKENS") or "24000"),
				int(os.environ.get("QUOTE_ASSESSMENT_OUTPUT_TOKENS") or "4096"),
			),
			TaskBudget(
				"embedding",
				int(os.environ.get("QUOTE_EMBEDDING_INPUT_TOKENS") or "32000"),
				0,
			),
		),
		packs=load_packs(),
		razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID", ""),
		razorpay_key_secret=os.environ.get("RAZORPAY_KEY_SECRET", ""),
		razorpay_webhook_secret=os.environ.get("RAZORPAY_WEBHOOK_SECRET", ""),
		admin_token=os.environ.get("ADMIN_TOKEN", ""),
		enterprise_sales_email=os.environ.get("ENTERPRISE_SALES_EMAIL")
		or "sales@skillsignal.app",
	)


def load_packs() -> tuple[RazorpayPack, ...]:
	raw = os.environ.get("RAZORPAY_PACKS", "")
	if not raw.strip():
		return _default_packs()
	parsed = json.loads(raw)
	if not isinstance(parsed, list):
		raise ValueError("RAZORPAY_PACKS must be a JSON array of packs")
	packs: list[RazorpayPack] = []
	for entry in parsed:
		if not isinstance(entry, dict):
			raise ValueError("Each Razorpay pack must be a JSON object")
		pack = RazorpayPack(
			id=str(entry["id"]),
			points=int(entry["points"]),
			amount_inr=int(entry["amountInr"]),
		)
		if pack.points <= 0 or pack.amount_inr <= 0:
			raise ValueError("Razorpay pack points and amount must be positive")
		packs.append(pack)
	if not packs:
		raise ValueError("RAZORPAY_PACKS must define at least one pack")
	return tuple(packs)
