import type { OpenRouterClient } from "../openrouter.ts";
import { JOB_REQUIREMENTS_SYSTEM_PROMPT } from "../extraction/prompt.ts";
import { blocksForModel, sourceBlocks } from "./compiler.ts";

export const extractJobRequirements = async (client: OpenRouterClient, options: { model: string; sourceText: string; maxOutputTokens?: number }): Promise<Record<string, unknown>> => {
	const blocks = blocksForModel(sourceBlocks(options.sourceText));
	const raw = await client.completeJson({
		model: options.model,
		systemPrompt: JOB_REQUIREMENTS_SYSTEM_PROMPT,
		userContent: `<job_description_data>\n${JSON.stringify({ documentType: "job_description", blocks })}\n</job_description_data>`,
		schemaName: "job_requirement_drafts",
		schema: { type: "object", properties: {
			requirements: { type: "array", items: { type: "object", properties: {
				normalizedText: { type: "string" }, category: { type: "string" }, suggestedKind: { type: "string" },
				sourceModality: { type: "string" }, assessability: { type: "string" },
				predicate: { type: "object" }, evidence: { type: "array", items: { type: "object", properties: { blockId: { type: "string" }, quote: { type: "string" } } } },
				confidence: { type: "number" },
			} } },
			warnings: { type: "array", items: { type: "string" } },
		} },
		maxOutputTokens: options.maxOutputTokens ?? 4096,
	});
	if (!Array.isArray(raw["requirements"])) throw new Error("Model job requirements do not match the schema");
	return raw;
};
