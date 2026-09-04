import { z } from "zod";

const evidenceQuote = z.object({ blockId: z.string().min(1).max(128), quote: z.string().min(1).max(2000) });

export const resumeExtractionSchema = z.object({
	schemaVersion: z.literal("3"),
	contact: z.object({
		name: z.string().max(256).nullable(),
		email: z.string().max(320).nullable(),
		phone: z.string().max(64).nullable(),
		location: z.string().max(256).nullable(),
		evidence: z.array(evidenceQuote).max(20),
	}),
	skills: z.array(z.object({
		canonicalName: z.string().min(1).max(128),
		sourceText: z.string().min(1).max(1000),
		evidence: z.array(evidenceQuote).min(1).max(20),
	})).max(200),
	employment: z.array(z.object({
		employer: z.string().max(256).nullable(),
		title: z.string().max(256).nullable(),
		startDate: z.string().regex(/^\d{4}(-\d{2})?$/).nullable(),
		endDate: z.string().regex(/^\d{4}(-\d{2})?$/).nullable(),
		isCurrent: z.boolean(),
		evidence: z.array(evidenceQuote).min(1).max(20),
	})).max(100),
	education: z.array(z.object({
		institution: z.string().max(256).nullable(),
		degree: z.string().max(256).nullable(),
		fieldOfStudy: z.string().max(256).nullable(),
		graduationDate: z.string().regex(/^\d{4}(-\d{2})?$/).nullable(),
		evidence: z.array(evidenceQuote).min(1).max(20),
	})).max(50),
	certifications: z.array(z.object({
		name: z.string().min(1).max(256),
		issuer: z.string().max(256).nullable(),
		evidence: z.array(evidenceQuote).min(1).max(20),
	})).max(100),
	suggestions: z.array(z.object({
		title: z.string().min(1).max(200),
		detail: z.string().min(1).max(1000),
		evidence: z.array(evidenceQuote).min(1).max(20),
	})).max(10).default([]),
	warnings: z.array(z.string()).max(50).default([]),
});

export const assessmentOutputSchema = z.object({
	assessments: z.array(z.object({
		requirementId: z.string().min(1).max(128),
		outcome: z.enum(["met", "partial", "not_met", "unknown"]),
		confidence: z.number().min(0).max(1),
		reasoning: z.string().min(1).max(2000),
		evidence: z.array(evidenceQuote).max(20).default([]),
	})).max(200),
});

export type ResumeExtraction = z.infer<typeof resumeExtractionSchema>;
export type AssessmentOutput = z.infer<typeof assessmentOutputSchema>;

const tighten = (node: unknown): unknown => {
	if (Array.isArray(node)) return node.map(tighten);
	if (typeof node === "object" && node !== null) {
		const record = node as Record<string, unknown>;
		const tightened: Record<string, unknown> = {};
		for (const [key, value] of Object.entries(record)) tightened[key] = tighten(value);
		if (typeof tightened["properties"] === "object" && tightened["properties"] !== null) {
			tightened["required"] = Object.keys(tightened["properties"] as Record<string, unknown>);
			tightened["additionalProperties"] = false;
		}
		return tightened;
	}
	return node;
};

export const strictJsonSchema = (schema: Record<string, unknown>): Record<string, unknown> =>
	tighten(schema) as Record<string, unknown>;

export const resumeExtractionJsonSchema = (): Record<string, unknown> => strictJsonSchema({
	type: "object",
	properties: {
		schemaVersion: { type: "string", const: "3" },
		contact: { type: "object", properties: {
			name: { type: ["string", "null"] }, email: { type: ["string", "null"] },
			phone: { type: ["string", "null"] }, location: { type: ["string", "null"] },
			evidence: { type: "array", items: { type: "object", properties: { blockId: { type: "string" }, quote: { type: "string" } } } },
		} },
		skills: { type: "array", items: { type: "object", properties: {
			canonicalName: { type: "string" }, sourceText: { type: "string" },
			evidence: { type: "array", items: { type: "object", properties: { blockId: { type: "string" }, quote: { type: "string" } } } },
		} } },
		employment: { type: "array", items: { type: "object", properties: {
			employer: { type: ["string", "null"] }, title: { type: ["string", "null"] },
			startDate: { type: ["string", "null"] }, endDate: { type: ["string", "null"] },
			isCurrent: { type: "boolean" },
			evidence: { type: "array", items: { type: "object", properties: { blockId: { type: "string" }, quote: { type: "string" } } } },
		} } },
		education: { type: "array", items: { type: "object", properties: {
			institution: { type: ["string", "null"] }, degree: { type: ["string", "null"] },
			fieldOfStudy: { type: ["string", "null"] }, graduationDate: { type: ["string", "null"] },
			evidence: { type: "array", items: { type: "object", properties: { blockId: { type: "string" }, quote: { type: "string" } } } },
		} } },
		certifications: { type: "array", items: { type: "object", properties: {
			name: { type: "string" }, issuer: { type: ["string", "null"] },
			evidence: { type: "array", items: { type: "object", properties: { blockId: { type: "string" }, quote: { type: "string" } } } },
		} } },
		suggestions: { type: "array", items: { type: "object", properties: {
			title: { type: "string" }, detail: { type: "string" },
			evidence: { type: "array", items: { type: "object", properties: { blockId: { type: "string" }, quote: { type: "string" } } } },
		} } },
		warnings: { type: "array", items: { type: "string" } },
	},
});
