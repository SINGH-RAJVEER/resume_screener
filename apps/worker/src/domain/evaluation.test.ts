import { describe, expect, test } from "bun:test";
import { summarize } from "./evaluation.ts";

describe("evaluation summary", () => {
	test("excludes unknown and hard gates from score while applying eligibility", () => {
		const assessments = [
			{ requirementId: "a", outcome: "met" as const, confidence: 1, reasoning: "", evidence: [] },
			{ requirementId: "b", outcome: "unknown" as const, confidence: 0, reasoning: "", evidence: [] },
			{ requirementId: "gate", outcome: "not_met" as const, confidence: 1, reasoning: "", evidence: [] },
		];
		const result = summarize(assessments, [{ kind: "required", weight: 2 }, { kind: "preferred", weight: 1 }, { kind: "hard_gate", weight: 1 }]);
		expect(result.score).toBe(100);
		expect(result.evidenceCoverage).toBe(50);
		expect(result.eligibility).toBe("not_eligible");
	});
});
