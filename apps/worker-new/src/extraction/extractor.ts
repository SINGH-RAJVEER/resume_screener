import type { OpenRouterClient } from "../openrouter.ts";
import { ASSESSMENT_SYSTEM_PROMPT, EXTRACTION_SYSTEM_PROMPT } from "./prompt.ts";
import { assessmentOutputSchema, resumeExtractionJsonSchema, resumeExtractionSchema } from "./schemas.ts";

export const extractResumeFacts = async (client: OpenRouterClient, options: { model: string; blocks: unknown; maxOutputTokens?: number }): Promise<Record<string, unknown>> => {
	const raw = await client.completeJson({
		model: options.model,
		systemPrompt: EXTRACTION_SYSTEM_PROMPT,
		userContent: `<resume_blocks>${JSON.stringify(options.blocks)}</resume_blocks>`,
		schemaName: "resume_extraction",
		schema: resumeExtractionJsonSchema(),
		maxOutputTokens: options.maxOutputTokens ?? 4096,
	});
	const parsed = resumeExtractionSchema.safeParse(raw);
	if (!parsed.success) throw new Error("Model extraction does not match the schema");
	return parsed.data as unknown as Record<string, unknown>;
};

export const assessRequirements = async (client: OpenRouterClient, options: { model: string; requirement: unknown; blocks: unknown; maxOutputTokens?: number }): Promise<Array<Record<string, unknown>>> => {
	const raw = await client.completeJson({
		model: options.model,
		systemPrompt: ASSESSMENT_SYSTEM_PROMPT,
		userContent: JSON.stringify({ requirement: options.requirement, blocks: options.blocks }),
		schemaName: "requirement_assessment",
		schema: { type: "object", properties: { assessments: { type: "array", items: { type: "object", properties: {
			requirementId: { type: "string" }, outcome: { type: "string" }, confidence: { type: "number" },
			reasoning: { type: "string" }, evidence: { type: "array", items: { type: "object", properties: { blockId: { type: "string" }, quote: { type: "string" } } } },
		} } } } },
		maxOutputTokens: options.maxOutputTokens ?? 2048,
	});
	const parsed = assessmentOutputSchema.safeParse(raw);
	if (!parsed.success) throw new Error("Model assessment does not match the schema");
	return parsed.data.assessments as unknown as Array<Record<string, unknown>>;
};

export const withModelFallback = async <T>(models: readonly string[], run: (model: string) => Promise<T>): Promise<{ result: T; model: string }> => {
	let lastError: unknown = null;
	for (const model of models) {
		try {
			return { result: await run(model), model };
		} catch (cause) {
			lastError = cause;
		}
	}
	throw lastError instanceof Error ? lastError : new Error("All configured models failed");
};
