import { createHash } from "node:crypto";

export const textHash = (text: string): string =>
	createHash("sha256").update(text, "utf8").digest("hex").slice(0, 32);

export const cosineSimilarity = (a: readonly number[], b: readonly number[]): number => {
	if (a.length !== b.length || !a.length) return 0;
	let dot = 0;
	let normA = 0;
	let normB = 0;
	for (let index = 0; index < a.length; index++) {
		dot += (a[index] as number) * (b[index] as number);
		normA += (a[index] as number) * (a[index] as number);
		normB += (b[index] as number) * (b[index] as number);
	}
	if (!normA || !normB) return 0;
	return dot / (Math.sqrt(normA) * Math.sqrt(normB));
};

export const topSemanticMatches = (
	requirementVector: readonly number[],
	blockVectors: Readonly<Record<string, readonly number[]>>,
	options: { limit?: number; minSimilarity?: number } = {},
): Array<{ blockId: string; similarity: number }> => {
	const limit = options.limit ?? 3;
	const minSimilarity = options.minSimilarity ?? 0.3;
	return Object.entries(blockVectors)
		.map(([blockId, vector]) => ({ blockId, similarity: Math.round(cosineSimilarity(requirementVector, vector) * 10000) / 10000 }))
		.filter((item) => item.similarity >= minSimilarity)
		.sort((left, right) => right.similarity - left.similarity)
		.slice(0, limit);
};
