import { describe, expect, test } from "bun:test";
import { compileJobDescription, experienceMonths, sourceBlocks } from "./compiler.ts";

describe("job description compiler", () => {
	test("extracts deterministic requirements from the requirements section", () => {
		const artifact = compileJobDescription("Requirements\n- Must have Python and 3 years experience\n- Preferred: AWS certification") as { requirements: Array<Record<string, unknown>>; qualityState: string; warnings: string[] };
		expect(artifact.requirements.length).toBeGreaterThan(0);
		expect(artifact.requirements.some((item) => String(item["normalizedText"]).includes("Python"))).toBe(true);
	});

	test("omits prohibited criteria with a warning", () => {
		const artifact = compileJobDescription("Requirements\n- Must be under age 30 with Python") as { requirements: unknown[]; warnings: string[] };
		expect(artifact.requirements).toEqual([]);
		expect(artifact.warnings.some((warning) => warning.includes("prohibited"))).toBe(true);
	});

	test("splits source text into headed blocks with stable ids", () => {
		const blocks = sourceBlocks("About us\nWe build tools.\n\nRequirements\n- Python services");
		expect(blocks[blocks.length - 1]?.section).toBe("requirements");
		expect(blocks[blocks.length - 1]?.id).toMatch(/^jd-b\d+$/);
	});

	test("parses digit and word experience thresholds", () => {
		expect(experienceMonths("5 years of Python")).toBe(60);
		expect(experienceMonths("three years experience")).toBe(36);
		expect(experienceMonths("no threshold here")).toBeNull();
	});
});
