import { mentionedSkills } from "./vocabulary.ts";

const MAX_LISTED_GAPS = 8;
interface Data {
	readonly [key: string]: unknown;
	readonly contact?: unknown;
	readonly skills?: unknown;
	readonly employment?: unknown;
	readonly education?: unknown;
	readonly certifications?: unknown;
	readonly name?: unknown;
	readonly email?: unknown;
	readonly location?: unknown;
	readonly canonicalName?: unknown;
}
export interface Suggestion { readonly title: string; readonly detail: string }

export function independentReport(facts: Data, jobDescription: string | null): { score: number; suggestions: Suggestion[] } {
	const contact = isRecord(facts.contact) ? facts.contact : {};
	const skills = documentedSkillNames(facts);
	const suggestions = readinessSuggestions(contact, skills, facts);
	if (jobDescription) suggestions.push(...roleAlignmentSuggestions(jobDescription, skills));
	return { score: readinessScore(contact, skills, facts), suggestions };
}

export function documentedSkillNames(facts: Data): Set<string> {
	return new Set(entries(facts.skills).map((item) => item.canonicalName).filter((value): value is string => typeof value === "string"));
}

export function readinessSuggestions(contact: Data, skills: Set<string>, facts: Data): Suggestion[] {
	const suggestions: Suggestion[] = [];
	if (!contact.name) suggestions.push({ title: "Add a clear name", detail: "Start the resume with your name." });
	if (!contact.email) suggestions.push({ title: "Add contact details", detail: "Include a professional email address." });
	if (!skills.size) suggestions.push({ title: "Make skills easier to verify", detail: "Name the tools and technologies you used in your experience." });
	if (!entries(facts.employment).length) suggestions.push({ title: "Document your experience", detail: "List each role with the employer, title, and dates so your experience can be verified." });
	if (!entries(facts.education).length && !entries(facts.certifications).length) suggestions.push({ title: "Add education or certifications", detail: "Include degrees or credentials with their issuing institutions and dates." });
	return suggestions;
}

export function roleAlignmentSuggestions(jobDescription: string, documented: Set<string>): Suggestion[] {
	const missing = [...mentionedSkills(jobDescription)].filter((skill) => !documented.has(skill)).sort();
	return missing.length ? [{ title: "Review role-specific evidence", detail: `The job description mentions ${missing.slice(0, MAX_LISTED_GAPS).join(", ")}. Add them only when your resume already supports the claim.` }] : [{ title: "Connect experience to the role", detail: "Use specific outcomes to show how your documented skills apply to this role." }];
}

export function readinessScore(contact: Data, skills: Set<string>, facts: Data): number {
	return Math.min(100, 20 + (contact.name ? 15 : 0) + (contact.email ? 15 : 0) + (contact.location ? 10 : 0) + Math.min(25, skills.size * 5) + (entries(facts.employment).length ? 5 : 0) + (entries(facts.education).length ? 3 : 0) + (entries(facts.certifications).length ? 2 : 0));
}

function entries(value: unknown): Data[] { return Array.isArray(value) ? value.filter(isRecord) : []; }
function isRecord(value: unknown): value is Data { return typeof value === "object" && value !== null && !Array.isArray(value); }
