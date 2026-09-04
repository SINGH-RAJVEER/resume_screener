import { describe, expect, test } from "bun:test";
import { cosineSimilarity, topSemanticMatches } from "./semantic.ts";

describe("semantic matching", () => {
	test("returns one for identical vectors and zero for mismatched lengths", () => {
		expect(cosineSimilarity([1, 0], [1, 0])).toBeCloseTo(1);
		expect(cosineSimilarity([1, 0], [1, 0, 0])).toBe(0);
		expect(cosineSimilarity([0, 0], [1, 0])).toBe(0);
	});

	test("ranks similar blocks above the threshold", () => {
		const matches = topSemanticMatches([1, 0], { a: [1, 0], b: [0, 1], c: [0.9, 0.1] });
		expect(matches.map((item) => item.blockId)).toEqual(["a", "c"]);
	});
});
