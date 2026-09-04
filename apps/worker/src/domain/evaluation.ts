import { employmentIntervals } from "./intervals.ts";
import { mentionedSkills } from "./vocabulary.ts";

export type Outcome = "met" | "partial" | "not_met" | "unknown";
export type Eligibility = "eligible" | "needs_review" | "not_eligible";
export interface Assessment { readonly requirementId: string; readonly outcome: Outcome; readonly confidence: number; readonly reasoning: string; readonly evidence: readonly Record<string, string>[] }
export interface EvaluationResult { readonly assessments: readonly Assessment[]; readonly score: number | null; readonly evidenceCoverage: number; readonly eligibility: Eligibility }
interface Data {
	readonly [key: string]: unknown;
	readonly canonicalName?: unknown;
	readonly evidenceBlockIds?: unknown;
	readonly skills?: unknown;
	readonly employment?: unknown;
	readonly education?: unknown;
	readonly certifications?: unknown;
	readonly contact?: unknown;
	readonly kind?: unknown;
	readonly weight?: unknown;
	readonly id?: unknown;
	readonly assessability?: unknown;
	readonly predicate?: unknown;
	readonly normalized_text?: unknown;
	readonly criteria?: unknown;
	readonly operator?: unknown;
	readonly type?: unknown;
	readonly minimumMonths?: unknown;
	readonly minimumLevel?: unknown;
	readonly name?: unknown;
	readonly degree?: unknown;
	readonly requirementId?: unknown;
	readonly outcome?: unknown;
	readonly confidence?: unknown;
	readonly evidence?: unknown;
	readonly blockId?: unknown;
	readonly quote?: unknown;
	readonly reasoning?: unknown;
}

const YEARS_PATTERN = /(\d+)\s*\+?\s*years?/i;
const EDUCATION_LEVELS: Record<string, readonly string[]> = { doctorate: ["phd", "doctorate", "d.litt", "dphil"], master: ["master", "m.tech", "mtech", "m.sc", "msc", "mba", "m.a.", "m.a"], bachelor: ["bachelor", "b.tech", "btech", "b.sc", "bsc", "b.e.", "b.a."] };

export function evaluate(normalizedFacts: Data, requirements: readonly Data[]): EvaluationResult {
	const skills = new Map<string, string[]>();
	for (const skill of entries(normalizedFacts.skills)) {
		const name = stringValue(skill.canonicalName);
		if (name) skills.set(name, strings(skill.evidenceBlockIds));
	}
	const assessments = requirements.map((requirement) => assessRequirement(requirement, skills, normalizedFacts));
	return summarize(assessments, requirements);
}

export function summarize(assessments: readonly Assessment[], requirements: readonly Data[]): EvaluationResult {
	const scored = assessments.map((assessment, index) => ({ assessment, requirement: requirements[index] })).filter((item): item is { assessment: Assessment; requirement: Data } => item.requirement !== undefined && !["ignored", "hard_gate"].includes(stringValue(item.requirement.kind)));
	const known = scored.filter(({ assessment }) => assessment.outcome !== "unknown");
	const denominator = known.reduce((sum, item) => sum + numberValue(item.requirement.weight), 0);
	const numerator = known.reduce((sum, item) => sum + numberValue(item.requirement.weight) * outcomeValue(item.assessment.outcome), 0);
	const hardGates = assessments.filter((_, index) => stringValue(requirements[index]?.kind) === "hard_gate");
	const eligibility: Eligibility = hardGates.some((item) => item.outcome === "not_met") ? "not_eligible" : hardGates.some((item) => item.outcome === "partial" || item.outcome === "unknown") ? "needs_review" : "eligible";
	return { assessments, score: denominator ? Math.round(100 * numerator / denominator) : null, evidenceCoverage: scored.length ? Math.round(100 * known.length / scored.length) : 100, eligibility };
}

export function assessRequirement(requirement: Data, skills: ReadonlyMap<string, readonly string[]>, facts: Data = {}): Assessment {
	const id = stringValue(requirement.id);
	if (stringValue(requirement.assessability, "resume_evidence") !== "resume_evidence") return assessment(id, "unknown", 0, "This requirement cannot be assessed from resume evidence.");
	const predicate = record(requirement.predicate);
	if (Array.isArray(predicate.criteria) && predicate.criteria.length) return assessPredicate(id, predicate, skills, facts);
	const text = stringValue(requirement.normalized_text);
	const required = mentionedSkills(text);
	if (required.size) return assessSkills(id, required, skills);
	const years = text.match(YEARS_PATTERN);
	if (years?.[1]) return assessExperienceMonths(id, Number(years[1]) * 12, facts);
	const certification = findCertification(text, facts);
	if (certification) return assessment(id, "met", 1, "Documented certification matches the requirement.", [{ blockId: "facts", quote: certification }]);
	const education = findEducationLevel(text, facts);
	if (education) return assessment(id, education.outcome, 1, education.reasoning);
	return assessment(id, "unknown", 0, "No deterministic criterion match.");
}

function assessPredicate(id: string, predicate: Data, skills: ReadonlyMap<string, readonly string[]>, facts: Data): Assessment {
	const criteria = predicate.criteria as unknown[];
	const assessments = criteria.filter(isRecord).map((criterion) => assessCriterion(id, criterion, skills, facts));
	if (!assessments.length) return assessment(id, "unknown", 0, "Requirement predicate is invalid.");
	const outcomes = assessments.map((item) => item.outcome);
	const any = stringValue(predicate.operator, "all_of") === "any_of";
	let outcome: Outcome;
	if (any) outcome = outcomes.includes("met") ? "met" : outcomes.includes("partial") ? "partial" : outcomes.every((item) => item === "not_met") ? "not_met" : "unknown";
	else outcome = outcomes.every((item) => item === "met") ? "met" : outcomes.includes("not_met") ? "not_met" : outcomes.some((item) => item === "met" || item === "partial") ? "partial" : "unknown";
	const reasoning = outcome === "met" ? (any ? "At least one allowed path is documented." : "All required parts are documented.") : outcome === "partial" ? "Only part of the requirement is documented." : "The complete requirement cannot be established from the resume.";
	return assessment(id, outcome, Math.min(...assessments.map((item) => item.confidence)), reasoning, assessments.flatMap((item) => item.evidence));
}

function assessCriterion(id: string, criterion: Data, skills: ReadonlyMap<string, readonly string[]>, facts: Data): Assessment {
	switch (stringValue(criterion.type)) {
		case "skill": { const name = stringValue(criterion.canonicalName); const blocks = skills.get(name) ?? []; return blocks.length ? assessment(id, "met", 1, `Documented evidence names ${name}.`, blocks.map((blockId) => ({ blockId, quote: name }))) : assessment(id, "unknown", 0, `The resume does not establish whether the candidate has ${name} experience.`); }
		case "experience": return assessExperienceMonths(id, integerValue(criterion.minimumMonths), facts);
		case "education": return assessEducationCriterion(id, stringValue(criterion.minimumLevel), facts);
		case "certification": return assessCertificationCriterion(id, stringValue(criterion.canonicalName), facts);
		default: return assessment(id, "unknown", 0, "This criterion needs evidence review.");
	}
}

function assessSkills(id: string, required: Set<string>, skills: ReadonlyMap<string, readonly string[]>): Assessment {
	const matched = [...required].sort().flatMap((skill) => { const blocks = skills.get(skill) ?? []; return blocks.length ? [{ skill, blocks }] : []; });
	const evidence = matched.flatMap(({ skill, blocks }) => blocks.map((blockId) => ({ blockId, quote: skill })));
	return matched.length === required.size ? assessment(id, "met", 1, "All explicit skill evidence found.", evidence) : matched.length ? assessment(id, "partial", 1, "Some explicit skill evidence found.", evidence) : assessment(id, "unknown", 0, "The resume does not establish whether the required skill is held.");
}

function assessExperienceMonths(id: string, needed: number, facts: Data): Assessment {
	const total = employmentIntervals(facts.employment).totalMonths;
	if (!total) return assessment(id, "unknown", 0, "No dated employment is documented to compute experience.");
	const outcome: Outcome = total >= needed ? "met" : total >= Math.floor(needed / 2) ? "partial" : "unknown";
	return assessment(id, outcome, outcome === "unknown" ? 0 : 1, `Documented employment totals ${Math.floor(total / 12)}y ${total % 12}m against ${needed / 12} years required.`);
}

function assessEducationCriterion(id: string, minimum: string, facts: Data): Assessment {
	const ranks: Record<string, number> = { bachelor: 1, master: 2, doctorate: 3 };
	const requested = ranks[minimum];
	const documented = documentedEducationLevels(facts);
	if (requested === undefined) return assessment(id, "unknown", 0, "Education level is unclear.");
	if (!documented.size) return assessment(id, "unknown", 0, "No education level is documented.");
	return assessment(id, Math.max(...[...documented].map((level) => ranks[level] ?? 0)) >= requested ? "met" : "partial", 1, Math.max(...[...documented].map((level) => ranks[level] ?? 0)) >= requested ? "Documented education meets or exceeds the requested level." : "Education is documented below the requested level.");
}

function assessCertificationCriterion(id: string, name: string, facts: Data): Assessment {
	const normalized = normalizeCredentialName(name);
	const found = entries(facts.certifications).find((item) => normalizeCredentialName(stringValue(item.name)) === normalized);
	return found ? assessment(id, "met", 1, "The required certification is documented.", [{ blockId: "facts", quote: stringValue(found.name) }]) : assessment(id, "unknown", 0, "The resume does not establish whether the certification is held.");
}

function findCertification(text: string, facts: Data): string | null { const lower = text.toLowerCase(); return entries(facts.certifications).map((item) => stringValue(item.name)).find((name) => name.length >= 4 && (lower.includes(name.toLowerCase()) || name.toLowerCase().split(" ").some((token) => token.length >= 3 && (` ${lower} `).includes(` ${token} `)))) ?? null; }
function findEducationLevel(text: string, facts: Data): { outcome: Outcome; reasoning: string } | null { const lower = text.toLowerCase(); const requested = Object.entries(EDUCATION_LEVELS).filter(([, words]) => words.some((word) => lower.includes(word))).map(([level]) => level); if (!requested.length && !lower.includes("degree")) return null; const documented = documentedEducationLevels(facts); if (!requested.length) return { outcome: "met", reasoning: "A degree is documented." }; return documented.size && requested.some((level) => documented.has(level)) ? { outcome: "met", reasoning: "Documented education includes the requested level." } : documented.size ? { outcome: "partial", reasoning: "Education is documented but at a different level than requested." } : { outcome: "not_met", reasoning: "No matching education level is documented." }; }
function documentedEducationLevels(facts: Data): Set<string> { const result = new Set<string>(); for (const item of entries(facts.education)) for (const [level, words] of Object.entries(EDUCATION_LEVELS)) if (words.some((word) => stringValue(item.degree).toLowerCase().includes(word))) result.add(level); return result; }
export function normalizeCredentialName(value: string): string { return value.toLowerCase().match(/[a-z0-9]+/g)?.join(" ") ?? ""; }
export function outcomeValue(outcome: Outcome): number { return { met: 1, partial: 0.5, not_met: 0, unknown: 0 }[outcome]; }
export function refineAssessments(deterministic: readonly Assessment[], modelAssessments: readonly Data[], requirements: readonly Data[]): Assessment[] {
	const byId = new Map(modelAssessments.map((item) => [stringValue(item.requirementId), item]));
	return deterministic.map((item, index) => {
		const model = byId.get(stringValue(requirements[index]?.id));
		if (!model) return item;
		const modelOutcome = stringValue(model.outcome, "unknown") as Outcome;
		const outcome = item.outcome === "met" && modelOutcome !== "met" ? "met" : modelOutcome;
		const confidence = Math.max(0, Math.min(numberValue(model.confidence), 1));
		const evidence = entries(model.evidence).map((item) => ({ blockId: stringValue(item.blockId), quote: stringValue(item.quote) })).filter((item) => item.blockId && item.quote);
		return assessment(item.requirementId, outcome, confidence, stringValue(model.reasoning) || item.reasoning, evidence.length ? evidence : item.evidence);
	});
}
function assessment(requirementId: string, outcome: Outcome, confidence: number, reasoning: string, evidence: readonly Record<string, string>[] = []): Assessment { return { requirementId, outcome, confidence, reasoning, evidence }; }
function entries(value: unknown): Data[] { return Array.isArray(value) ? value.filter(isRecord) : []; }
function isRecord(value: unknown): value is Data { return typeof value === "object" && value !== null && !Array.isArray(value); }
function record(value: unknown): Data { return isRecord(value) ? value : {}; }
function stringValue(value: unknown, fallback = ""): string { return typeof value === "string" ? value : fallback; }
function numberValue(value: unknown): number { return typeof value === "number" && Number.isFinite(value) ? value : 0; }
function integerValue(value: unknown): number { return typeof value === "number" && Number.isInteger(value) ? value : -1; }
function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []; }
