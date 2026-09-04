export const settlePoints = (promptTokens: number, completionTokens: number, reportedCostUsd: number, kind: string, settings: { pointsPerUsd: number; minimumIndependentEvaluationPoints: number; minimumEmployerResumePoints: number; priceCeilingUsdPerMillionInput: number; priceCeilingUsdPerMillionOutput: number }): number => {
	const minimum = kind === "independent_evaluation" ? settings.minimumIndependentEvaluationPoints : settings.minimumEmployerResumePoints;
	let cost = reportedCostUsd;
	if (!(cost > 0)) {
		cost = (promptTokens * settings.priceCeilingUsdPerMillionInput + completionTokens * settings.priceCeilingUsdPerMillionOutput) / 1_000_000;
	}
	return Math.max(minimum, Math.ceil(cost * settings.pointsPerUsd));
};
