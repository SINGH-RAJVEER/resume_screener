import { describe, expect, test } from "bun:test";
import { measureUnsupportedClaims } from "./claims.ts";

describe("unsupported claims", () => {
	test("flags values missing from cited quotes", () => {
		const report = measureUnsupportedClaims(
			{ skills: [{ canonicalName: "Python", sourceText: "Python", evidence: [{ blockId: "b1", quote: "Built Python services" }] }] },
			{ b1: "Built Python services" },
		);
		expect(report.totalClaims).toBe(2);
		expect(report.unsupportedClaims).toBe(0);
		expect(report.rate).toBe(0);
	});

	test("counts invalid citations when quotes are absent from blocks", () => {
		const report = measureUnsupportedClaims(
			{ skills: [{ canonicalName: "Go", sourceText: "Go", evidence: [{ blockId: "b1", quote: "Invented claim" }] }] },
			{ b1: "Built Python services" },
		);
		expect(report.unsupportedClaims).toBeGreaterThan(0);
		expect(report.examples.length).toBeGreaterThan(0);
	});
});
