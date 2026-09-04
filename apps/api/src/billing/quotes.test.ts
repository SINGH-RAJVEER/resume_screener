import { describe, expect, test } from "bun:test";
import { INDEPENDENT_QUOTE, UnknownQuoteKindError, pointQuote, settlePoints } from "./quotes.ts";

const settings = {
	pointsPerUsd: 1000,
	minimumIndependentEvaluationPoints: 10,
	minimumEmployerResumePoints: 5,
	priceCeilingUsdPerMillionInput: 3,
	priceCeilingUsdPerMillionOutput: 15,
	independentBudgets: [{ task: "extraction", maxInputTokens: 16000, maxOutputTokens: 4096 }],
	employerBudgets: [{ task: "extraction", maxInputTokens: 16000, maxOutputTokens: 4096 }],
};

describe("point quotes", () => {
	test("quotes the ceiling-bounded maximum with the minimum floor", () => {
		const quote = pointQuote(INDEPENDENT_QUOTE, settings);
		expect(quote.points).toBeGreaterThanOrEqual(quote.minimumPoints);
		expect(quote.costCeilingPoints).toBeGreaterThan(0);
	});

	test("rejects unknown quote kinds", () => {
		expect(() => pointQuote("other", settings)).toThrow(UnknownQuoteKindError);
	});

	test("settles to the minimum when no cost is reported", () => {
		expect(settlePoints(null, INDEPENDENT_QUOTE, settings)).toBe(10);
		expect(settlePoints(0.05, INDEPENDENT_QUOTE, settings)).toBe(50);
	});
});
