import { describe, expect, test } from "bun:test";
import { mentionedSkills } from "./vocabulary.ts";

describe("skill vocabulary", () => {
	test("matches aliases and punctuation without partial words", () => {
		expect(mentionedSkills("Amazon Web Services, k8s and Node.js; pythonic")).toEqual(new Set(["AWS", "Kubernetes", "Node.js"]));
	});
});
