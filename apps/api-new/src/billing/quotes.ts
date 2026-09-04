export const INDEPENDENT_QUOTE = "independent_evaluation";
export const EMPLOYER_QUOTE = "employer_resume";

export class UnknownQuoteKindError extends Error {}

export interface TaskBudget {
	task: string;
	maxInputTokens: number;
	maxOutputTokens: number;
}

export interface BillingSettings {
	pointsPerUsd: number;
	minimumIndependentEvaluationPoints: number;
	minimumEmployerResumePoints: number;
	priceCeilingUsdPerMillionInput: number;
	priceCeilingUsdPerMillionOutput: number;
	independentBudgets: readonly TaskBudget[];
	employerBudgets: readonly TaskBudget[];
}

export interface PointQuote {
	kind: string;
	lineItems: readonly TaskBudget[];
	costCeilingPoints: number;
	minimumPoints: number;
	points: number;
}

export const pointQuote = (kind: string, settings: BillingSettings): PointQuote => {
	const independent = kind === INDEPENDENT_QUOTE;
	if (!independent && kind !== EMPLOYER_QUOTE) throw new UnknownQuoteKindError(kind);
	const budgets = independent ? settings.independentBudgets : settings.employerBudgets;
	const minimum = independent ? settings.minimumIndependentEvaluationPoints : settings.minimumEmployerResumePoints;
	const costUsd = budgets.reduce((total, budget) => total + budget.maxInputTokens * settings.priceCeilingUsdPerMillionInput / 1_000_000 + budget.maxOutputTokens * settings.priceCeilingUsdPerMillionOutput / 1_000_000, 0);
	const costCeilingPoints = Math.ceil(costUsd * settings.pointsPerUsd);
	return { kind, lineItems: budgets, costCeilingPoints, minimumPoints: minimum, points: Math.max(minimum, costCeilingPoints) };
};

export const settlePoints = (reportedCostUsd: number | null | undefined, kind: string, settings: BillingSettings): number => {
	const minimum = kind === INDEPENDENT_QUOTE ? settings.minimumIndependentEvaluationPoints : settings.minimumEmployerResumePoints;
	return reportedCostUsd == null ? minimum : Math.max(minimum, Math.ceil(reportedCostUsd * settings.pointsPerUsd));
};
