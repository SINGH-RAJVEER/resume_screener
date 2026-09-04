export const CLAIM_TEXT_FIELDS: Record<string, readonly string[]> = {
	contact: ["name", "email", "phone", "location"],
	skills: ["canonicalName", "sourceText"],
	employment: ["employer", "title"],
	education: ["institution", "degree", "fieldOfStudy"],
	certifications: ["name"],
};

export type CollectionClaims = {
	readonly total: number;
	readonly invalidCitations: number;
	readonly ungroundedValues: number;
};

export type ClaimReport = {
	readonly collections: Readonly<Record<string, CollectionClaims>>;
	readonly examples: readonly string[];
	readonly totalClaims: number;
	readonly unsupportedClaims: number;
	readonly rate: number | null;
};

type Entry = Record<string, unknown>;

const entries = (value: unknown): Entry[] => {
	if (typeof value === "object" && value !== null && !Array.isArray(value)) return [value as Entry];
	if (!Array.isArray(value)) return [];
	return value.filter((item): item is Entry => typeof item === "object" && item !== null && !Array.isArray(item));
};

const validQuotes = (entry: Entry, blockTexts: Readonly<Record<string, string>>): string[] => {
	const evidence = entry["evidence"];
	if (!Array.isArray(evidence)) return [];
	const quotes: string[] = [];
	for (const item of evidence) {
		if (typeof item !== "object" || item === null) continue;
		const citation = item as Entry;
		const quote = String(citation["quote"] ?? "");
		const blockText = blockTexts[String(citation["blockId"] ?? "")];
		if (!quote || blockText === undefined || !blockText.includes(quote)) continue;
		quotes.push(quote);
	}
	return quotes;
};

export const measureUnsupportedClaims = (facts: Readonly<Record<string, unknown>>, blockTexts: Readonly<Record<string, string>>): ClaimReport => {
	const collections: Record<string, CollectionClaims> = {};
	const examples: string[] = [];
	for (const [collection, textFields] of Object.entries(CLAIM_TEXT_FIELDS)) {
		let total = 0;
		let invalidCitations = 0;
		let ungroundedValues = 0;
		for (const entry of entries(facts[collection])) {
			const quotes = validQuotes(entry, blockTexts);
			for (const field of textFields) {
				const value = entry[field];
				if (typeof value !== "string" || !value.trim()) continue;
				total += 1;
				if (!quotes.length) {
					invalidCitations += 1;
					examples.push(`${collection}.${field}: ${value}`);
				} else if (!quotes.join("\n").toLowerCase().includes(value.toLowerCase())) {
					ungroundedValues += 1;
					examples.push(`${collection}.${field}: ${value}`);
				}
			}
		}
		if (total) collections[collection] = { total, invalidCitations, ungroundedValues };
	}
	const totalClaims = Object.values(collections).reduce((sum, item) => sum + item.total, 0);
	const unsupportedClaims = Object.values(collections).reduce((sum, item) => sum + item.invalidCitations + item.ungroundedValues, 0);
	return { collections, examples: examples.slice(0, 20), totalClaims, unsupportedClaims, rate: totalClaims ? unsupportedClaims / totalClaims : null };
};
