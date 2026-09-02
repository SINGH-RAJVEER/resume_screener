import corpus from "./skills_corpus.json";

export const TOKEN_PATTERN = /[a-z0-9]+(?:[.#/-]+[a-z0-9]+|[+#]+)*/g;
export const MAX_PHRASE_TOKENS = 6;

interface Corpus {
	readonly skills: readonly { readonly name: string; readonly category?: string | null }[];
	readonly aliases: Readonly<Record<string, string>>;
	readonly absorbers?: readonly string[];
}

export class SkillVocabulary {
	readonly phraseToCanonical: ReadonlyMap<string, string>;
	readonly categories: ReadonlyMap<string, string | null>;
	private readonly absorbers: ReadonlySet<string>;
	private readonly maxTokens: number;

	constructor(phrases: ReadonlyMap<string, string>, categories: ReadonlyMap<string, string | null>, absorbers: ReadonlySet<string>) {
		this.phraseToCanonical = phrases;
		this.categories = categories;
		this.absorbers = absorbers;
		this.maxTokens = Math.min(Math.max(...[...phrases.keys()].map((phrase) => phrase.split(" ").length)), MAX_PHRASE_TOKENS);
	}

	mention(text: string): Readonly<Record<string, readonly string[]>> {
		const tokens = tokenize(text);
		const found = new Map<string, string[]>();
		let index = 0;
		while (index < tokens.length) {
			let consumed = 0;
			for (let count = Math.min(this.maxTokens, tokens.length - index); count > 0; count -= 1) {
				const phrase = tokens.slice(index, index + count).join(" ");
				const canonical = this.phraseToCanonical.get(phrase);
				if (canonical !== undefined) {
					const spans = found.get(canonical) ?? [];
					if (!spans.includes(phrase)) spans.push(phrase);
					found.set(canonical, spans);
					consumed = count;
					break;
				}
				if (this.absorbers.has(phrase)) {
					consumed = count;
					break;
				}
			}
			index += consumed || 1;
		}
		return Object.fromEntries(found);
	}

	categoryFor(canonicalName: string): string | null {
		return this.categories.get(canonicalName.toLowerCase()) ?? null;
	}
}

let cached: SkillVocabulary | undefined;
export function loadVocabulary(): SkillVocabulary {
	if (cached) return cached;
	const data = corpus as Corpus;
	const categories = new Map<string, string | null>();
	const phrases = new Map<string, string>();
	for (const skill of data.skills) {
		const key = skill.name.toLowerCase();
		categories.set(key, skill.category ?? null);
		phrases.set(key, skill.name);
	}
	for (const [alias, canonical] of Object.entries(data.aliases)) {
		if (!categories.has(canonical.toLowerCase())) throw new Error(`Alias targets unknown skill: ${canonical}`);
		phrases.set(alias.toLowerCase(), canonical);
	}
	cached = new SkillVocabulary(phrases, categories, new Set((data.absorbers ?? []).map((item) => item.toLowerCase())));
	return cached;
}

export function mentionedSkills(text: string): Set<string> {
	return new Set(Object.keys(loadVocabulary().mention(text)));
}

export function tokenize(text: string): string[] {
	return text.toLowerCase().match(TOKEN_PATTERN) ?? [];
}
