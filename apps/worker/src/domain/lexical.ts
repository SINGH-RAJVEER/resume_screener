import { tokenize } from "./vocabulary.ts";

const STOP_TOKENS = new Set("a an and are as at be by for from in is of on or our that the to we will with you your".split(" "));

export function lexicalTokens(text: string): string[] {
	return tokenize(text).filter((token) => token.length > 1 && !STOP_TOKENS.has(token));
}

export interface LexicalMatch {
	readonly blockId: string;
	readonly score: number;
}

export function topLexicalMatches(requirementText: string, blockTexts: Readonly<Record<string, string>>, limit = 3, minScore = 0.08): LexicalMatch[] {
	const blocks = Object.entries(blockTexts).map(([blockId, text]) => ({ blockId, counts: counts(lexicalTokens(text)) })).filter((item) => item.counts.size > 0);
	if (blocks.length === 0) return [];
	const documentFrequency = new Map<string, number>();
	for (const block of blocks) for (const token of block.counts.keys()) documentFrequency.set(token, (documentFrequency.get(token) ?? 0) + 1);
	const idf = (token: string): number => Math.log((blocks.length + 1) / ((documentFrequency.get(token) ?? 0) + 1)) + 1;
	const vector = (input: ReadonlyMap<string, number>): Map<string, number> => new Map([...input].map(([token, count]) => [token, count * idf(token)]));
	const requirement = vector(counts(lexicalTokens(requirementText)));
	const norm = (input: ReadonlyMap<string, number>): number => Math.sqrt([...input.values()].reduce((sum, value) => sum + value * value, 0));
	const requirementNorm = norm(requirement);
	return blocks.map(({ blockId, counts: blockCounts }) => {
		const block = vector(blockCounts);
		const denominator = requirementNorm * norm(block);
		const dot = [...requirement].reduce((sum, [token, weight]) => sum + weight * (block.get(token) ?? 0), 0);
		return { blockId, score: denominator === 0 ? 0 : Math.round((dot / denominator) * 10000) / 10000 };
	}).filter((item) => item.score >= minScore).sort((left, right) => right.score - left.score).slice(0, limit);
}

function counts(tokens: readonly string[]): Map<string, number> {
	const result = new Map<string, number>();
	for (const token of tokens) result.set(token, (result.get(token) ?? 0) + 1);
	return result;
}
