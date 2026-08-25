from dataclasses import dataclass
from math import ceil

from .settings import BillingSettings, TaskBudget

INDEPENDENT_QUOTE = "independent_evaluation"
EMPLOYER_QUOTE = "employer_resume"


class UnknownQuoteKindError(Exception):
	pass


@dataclass(frozen=True)
class PointQuote:
	kind: str
	line_items: tuple[TaskBudget, ...]
	cost_ceiling_points: int
	minimum_points: int
	points: int


def point_quote(kind: str, settings: BillingSettings) -> PointQuote:
	if kind == INDEPENDENT_QUOTE:
		budgets = settings.independent_budgets
		minimum = settings.minimum_independent_evaluation_points
	elif kind == EMPLOYER_QUOTE:
		budgets = settings.employer_budgets
		minimum = settings.minimum_employer_resume_points
	else:
		raise UnknownQuoteKindError(kind)
	cost_usd = sum(
		budget.max_input_tokens
		* settings.price_ceiling_usd_per_million_input
		/ 1_000_000
		+ budget.max_output_tokens
		* settings.price_ceiling_usd_per_million_output
		/ 1_000_000
		for budget in budgets
	)
	cost_ceiling_points = ceil(cost_usd * settings.points_per_usd)
	return PointQuote(
		kind=kind,
		line_items=budgets,
		cost_ceiling_points=cost_ceiling_points,
		minimum_points=minimum,
		points=max(minimum, cost_ceiling_points),
	)


def settle_points(reported_cost_usd: float | None, kind: str, settings: BillingSettings) -> int:
	"""Completion charge: the greater of the minimum or the ceiling-rounded reported cost."""

	minimum = (
		settings.minimum_independent_evaluation_points
		if kind == INDEPENDENT_QUOTE
		else settings.minimum_employer_resume_points
	)
	if reported_cost_usd is None:
		return minimum
	return max(minimum, ceil(reported_cost_usd * settings.points_per_usd))
