import { loadVocabulary } from "./vocabulary.ts";

export interface ResumeBlock { readonly id: string; readonly text: string; readonly [key: string]: unknown }

export function normalizeResume(blocks: Iterable<ResumeBlock>): Record<string, unknown> {
	const blockList = [...blocks];
	const vocabulary = loadVocabulary();
	const skillHits = new Map<string, string[]>();
	for (const block of blockList) for (const name of Object.keys(vocabulary.mention(block.text))) {
		const ids = skillHits.get(name) ?? [];
		if (!ids.includes(block.id)) ids.push(block.id);
		skillHits.set(name, ids);
	}
	const order = new Map(blockList.map((block, index) => [block.id, index]));
	return {
		contact: contactFacts(blockList),
		skills: [...skillHits.keys()].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" })).map((canonicalName) => ({ canonicalName, category: vocabulary.categoryFor(canonicalName), evidenceBlockIds: [...(skillHits.get(canonicalName) ?? [])].sort((a, b) => (order.get(a) ?? blockList.length) - (order.get(b) ?? blockList.length)) })),
	};
}

export function contactFacts(blocks: Iterable<ResumeBlock>): { name: string | null; email: string | null; location: string | null } {
	const lines = [...blocks].flatMap((block) => block.text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean));
	const combined = lines.join("\n");
	const email = combined.match(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i)?.[0] ?? null;
	const first = lines[0] ?? "";
	const words = first.split(" ");
	const name = words.length >= 2 && words.length <= 5 && /^[A-Za-z][A-Za-z .'-]{1,80}$/.test(first) && words.every((word) => /^[A-Z]/.test(word)) ? first : null;
	const location = lines.slice(0, 12).find((line) => line.toLowerCase().startsWith("location:"))?.slice("Location:".length).trim() ?? null;
	return { name, email, location };
}
