import { normalizeResume, type ResumeBlock } from "../domain/normalizer.ts";
import { extractBlocks, type ParsedDocument } from "./parser.ts";

export interface PreparedDocument {
	artifact: ParsedDocument;
	normalizedFacts: Record<string, unknown>;
}

export async function prepareDocument(
	content: Uint8Array,
	mediaType: string,
): Promise<PreparedDocument> {
	const artifact = await extractBlocks(content, mediaType);
	const normalizedFacts = {
		...normalizeResume(artifact.blocks as unknown as ResumeBlock[]),
		warnings: [...artifact.quality.warnings],
	};
	return { artifact, normalizedFacts };
}

export function addDocumentWarnings(
	facts: Record<string, unknown>,
	warnings: readonly string[],
): Record<string, unknown> {
	const { warnings: existingValue } = facts;
	const existing = Array.isArray(existingValue) ? existingValue : [];
	return {
		...facts,
		warnings: [
			...new Set(
				[...warnings, ...existing].filter(
					(warning): warning is string => typeof warning === "string",
				),
			),
		],
	};
}

export type { EvidenceBlock, ParsedDocument } from "./parser.ts";
export { DocumentParseError, extractBlocks } from "./parser.ts";
