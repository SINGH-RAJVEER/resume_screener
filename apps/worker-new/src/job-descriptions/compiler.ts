import { createHash } from "node:crypto";
import { loadVocabulary, mentionedSkills } from "../domain/vocabulary.ts";
import { JOB_REQUIREMENTS_COMPILER_VERSION, JOB_REQUIREMENTS_PROMPT_VERSION, JOB_REQUIREMENTS_SCHEMA_VERSION } from "@skillsignal/server-core/versions";

export const MAX_DRAFT_REQUIREMENTS = 50;

const HEADING_SECTIONS: Record<string, string> = {
	requirements: "requirements",
	qualifications: "requirements",
	"minimum qualifications": "requirements",
	"what you bring": "requirements",
	"what we are looking for": "requirements",
	"what we're looking for": "requirements",
	"preferred qualifications": "preferred",
	"preferred skills": "preferred",
	"nice to have": "preferred",
	"nice-to-have": "preferred",
	"bonus points": "preferred",
	responsibilities: "responsibilities",
	"what you will do": "responsibilities",
	"what you'll do": "responsibilities",
	"about us": "about",
	"about the company": "about",
	benefits: "benefits",
	"what we offer": "benefits",
	"equal opportunity": "legal",
	"how to apply": "application",
};

const REQUIRED_CUE = /\b(must|required|minimum|need to|needs to|shall|essential)\b/i;
const PREFERRED_CUE = /\b(preferred|nice[ -]to[ -]have|bonus|plus|desirable|ideally)\b/i;
const YEARS_PATTERN = /\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b/i;
const WORD_YEARS_PATTERN = /\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+years?\b/i;
const NUMBER_WORDS: Record<string, number> = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10 };
const DEGREE_LEVELS: Record<string, readonly string[]> = {
	doctorate: ["phd", "doctorate", "doctoral", "dphil"],
	master: ["master", "mba", "mtech", "m.tech", "msc", "m.sc"],
	bachelor: ["bachelor", "undergraduate degree", "btech", "b.tech", "bsc", "b.sc"],
};
const PROHIBITED_PATTERN = /\b(age|gender|sex|race|ethnicity|religion|marital status|pregnan(?:t|cy)|disability|nationality|national origin|health|veteran status)\b/i;
const ATTESTATION_PATTERNS: Record<string, RegExp> = {
	work_authorization: /\b(work authorization|authorized to work|visa sponsorship|right to work)\b/i,
	location: /\b(relocat(?:e|ion)|reside in|based in|commutable distance)\b/i,
	schedule: /\b(night shift|weekends?|on[ -]call|travel|time zone|working hours)\b/i,
};
const SOFT_SKILL_PATTERN = /\b(communication|team player|self[ -]starter|leadership style|interpersonal)\b/i;
const CERTIFICATION_PATTERN = /\b(certification|certified|licen[cs]e|credential)\b/i;
const BULLET_PATTERN = /^\s*(?:[-*•▪◦]+|\d+[.)])\s+/;

export type JobBlock = {
	readonly id: string;
	readonly text: string;
	readonly section: string;
	readonly startOffset: number;
	readonly endOffset: number;
	readonly wasBullet: boolean;
};

export const sourceBlocks = (sourceText: string): JobBlock[] => {
	const blocks: JobBlock[] = [];
	let section = "unknown";
	let offset = 0;
	for (const rawLine of sourceText.split(/(?<=\n)/)) {
		const line = rawLine.replace(/\r?\n$/, "");
		const stripped = line.trim();
		const lineStart = offset;
		offset += rawLine.length;
		if (!stripped) continue;
		const headingKey = stripped.replace(/[:\s]+$/, "").toLowerCase();
		if (headingKey in HEADING_SECTIONS && stripped.length <= 80) {
			section = HEADING_SECTIONS[headingKey] as string;
			continue;
		}
		const bullet = BULLET_PATTERN.exec(line);
		const contentStart = bullet ? bullet[0].length : line.length - line.trimStart().length;
		const content = line.slice(contentStart).trim();
		if (content.length < 3) continue;
		const localStart = line.indexOf(content, contentStart);
		const start = lineStart + localStart;
		blocks.push({ id: `jd-b${blocks.length + 1}`, text: content, section, startOffset: start, endOffset: start + content.length, wasBullet: bullet !== null });
	}
	return blocks;
};

export const blocksForModel = (blocks: readonly JobBlock[]): Array<Record<string, string>> =>
	blocks.map((block) => ({ id: block.id, section: block.section, text: block.text }));

export const compileJobDescription = (sourceText: string, modelOutput?: Record<string, unknown> | null, options: { degraded?: boolean; degradedReason?: string | null } = {}): Record<string, unknown> => {
	const blocks = sourceBlocks(sourceText);
	const warnings: string[] = [];
	const candidates: Array<Record<string, unknown>> = deterministicCandidates(blocks, warnings);
	let degraded = options.degraded ?? false;
	if (modelOutput) {
		const [modelCandidates, modelWarnings] = groundedModelCandidates(modelOutput, blocks);
		warnings.push(...modelWarnings);
		candidates.push(...modelCandidates);
		if (!modelCandidates.length) {
			degraded = true;
			warnings.push("Model extraction produced no grounded requirements");
		}
	}
	const requirements = deduplicate(candidates, warnings).slice(0, MAX_DRAFT_REQUIREMENTS);
	if (candidates.length > MAX_DRAFT_REQUIREMENTS) warnings.push("Low-confidence requirements were omitted after the review limit");
	if (options.degradedReason) warnings.push(options.degradedReason);
	const qualityState = requirements.length && !warnings.length && !degraded ? "ready" : "review_required";
	if (!requirements.length) warnings.push("No explicit job requirements were found; add criteria manually");
	return {
		schemaVersion: JOB_REQUIREMENTS_SCHEMA_VERSION,
		compilerVersion: JOB_REQUIREMENTS_COMPILER_VERSION,
		promptVersion: JOB_REQUIREMENTS_PROMPT_VERSION,
		degraded,
		qualityState,
		warnings: uniqueStrings(warnings),
		requirements,
	};
};

const deterministicCandidates = (blocks: readonly JobBlock[], warnings: string[]): Array<Record<string, unknown>> => {
	const candidates: Array<Record<string, unknown>> = [];
	for (const block of blocks) {
		const text = normalizedStatement(block.text);
		if (["about", "benefits", "legal", "application"].includes(block.section)) continue;
		if (PROHIBITED_PATTERN.test(text)) {
			warnings.push(`Potentially prohibited criterion omitted from ${block.id}`);
			continue;
		}
		const skills = [...mentionedSkills(text)].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
		const hasCue = REQUIRED_CUE.test(text) || PREFERRED_CUE.test(text);
		const inRequirementSection = block.section === "requirements" || block.section === "preferred";
		if (block.section === "responsibilities" && !hasCue) continue;
		if (!inRequirementSection && !hasCue && !(block.wasBullet && skills.length)) continue;
		candidates.push(deterministicCandidate(block, text, skills));
	}
	return candidates;
};

const deterministicCandidate = (block: JobBlock, text: string, skills: readonly string[]): Record<string, unknown> => {
	const [suggestedKind, sourceModality] = inferImportance(block.section, text);
	const [category, assessability] = inferCategoryAndAssessability(text, skills);
	const predicate = inferPredicate(text, skills);
	const evidence = [{ blockId: block.id, quote: block.text, startOffset: block.startOffset, endOffset: block.endOffset, section: block.section }];
	const signals: string[] = [];
	if (block.section === "requirements" || block.section === "preferred") signals.push("section");
	if (skills.length) signals.push("taxonomy");
	if (REQUIRED_CUE.test(text) || PREFERRED_CUE.test(text)) signals.push("language_cue");
	const confidence = Math.min(0.92, 0.55 + 0.12 * signals.length);
	return finalizeCandidate({
		normalizedText: text,
		category,
		suggestedKind,
		suggestedWeight: suggestedKind === "required" ? 2 : 1,
		sourceModality,
		assessability,
		predicate,
		evidence,
		confidence,
		signals: signals.length ? signals : ["bullet"],
	});
};

const inferImportance = (section: string, text: string): [string, string] => {
	if (PREFERRED_CUE.test(text)) return ["preferred", "explicit_preferred"];
	if (REQUIRED_CUE.test(text)) return ["required", "explicit_required"];
	if (section === "preferred") return ["preferred", "section_preferred"];
	if (section === "requirements") return ["required", "section_required"];
	return ["preferred", "unclear"];
};

const inferCategoryAndAssessability = (text: string, skills: readonly string[]): [string, string] => {
	for (const [category, pattern] of Object.entries(ATTESTATION_PATTERNS)) {
		if (pattern.test(text)) return [category, "candidate_attestation"];
	}
	if (SOFT_SKILL_PATTERN.test(text)) return ["soft_skill", "recruiter_review"];
	if (experienceMonths(text) !== null) return ["experience", "resume_evidence"];
	if (educationLevel(text)) return ["education", "resume_evidence"];
	if (CERTIFICATION_PATTERN.test(text)) return ["certification", "resume_evidence"];
	if (skills.length) return ["skill", "resume_evidence"];
	return ["other", "unclear"];
};

const inferPredicate = (text: string, skills: readonly string[]): Record<string, unknown> => {
	const criteria: Array<Record<string, unknown>> = [];
	const minimumMonths = experienceMonths(text);
	if (minimumMonths !== null) {
		criteria.push({ type: "experience", canonicalName: null, minimumMonths, minimumLevel: null, subjects: [...skills] });
	} else if (skills.length) {
		for (const skill of skills) criteria.push({ type: "skill", canonicalName: skill, minimumMonths: null, minimumLevel: null, subjects: [] });
	}
	const level = educationLevel(text);
	if (level) criteria.push({ type: "education", canonicalName: null, minimumMonths: null, minimumLevel: level, subjects: [] });
	if (CERTIFICATION_PATTERN.test(text) && !criteria.length) {
		criteria.push({ type: "certification", canonicalName: text, minimumMonths: null, minimumLevel: null, subjects: [] });
	}
	if (!criteria.length) criteria.push({ type: "other", canonicalName: null, minimumMonths: null, minimumLevel: null, subjects: [] });
	return { operator: /\bor\b/i.test(text) ? "any_of" : "all_of", criteria };
};

type ModelExtraction = { requirements: Array<Record<string, unknown>>; warnings: string[] };

const groundedModelCandidates = (modelOutput: Record<string, unknown>, blocks: readonly JobBlock[]): [Array<Record<string, unknown>>, string[]] => {
	const byId = new Map(blocks.map((block) => [block.id, block]));
	const requirements = Array.isArray(modelOutput["requirements"]) ? modelOutput["requirements"] as Array<Record<string, unknown>> : null;
	if (!requirements) return [[], ["Model requirement output failed schema validation"]];
	const warnings = Array.isArray(modelOutput["warnings"]) ? (modelOutput["warnings"] as unknown[]).filter((item): item is string => typeof item === "string") : [];
	const candidates: Array<Record<string, unknown>> = [];
	let dropped = 0;
	for (const requirement of requirements) {
		const rawEvidence = Array.isArray(requirement["evidence"]) ? requirement["evidence"] as Array<Record<string, unknown>> : [];
		const evidence: Array<Record<string, unknown>> = [];
		for (const citation of rawEvidence) {
			const block = byId.get(String(citation["blockId"] ?? ""));
			if (!block) continue;
			const quote = String(citation["quote"] ?? "");
			const localStart = block.text.indexOf(quote);
			if (localStart < 0 || !quote) continue;
			evidence.push({ blockId: block.id, quote, startOffset: block.startOffset + localStart, endOffset: block.startOffset + localStart + quote.length, section: block.section });
		}
		if (!evidence.length || requirement["assessability"] === "prohibited") {
			dropped += 1;
			continue;
		}
		const predicate = normalizeModelPredicate((requirement["predicate"] ?? {}) as Record<string, unknown>);
		if (!modelPredicateSupported(predicate, evidence)) {
			dropped += 1;
			continue;
		}
		const kind = String(requirement["suggestedKind"] ?? "preferred");
		candidates.push(finalizeCandidate({
			normalizedText: normalizedStatement(String(requirement["normalizedText"] ?? "")),
			category: String(requirement["category"] ?? "other"),
			suggestedKind: kind,
			suggestedWeight: kind === "required" ? 2 : 1,
			sourceModality: String(requirement["sourceModality"] ?? "unclear"),
			assessability: String(requirement["assessability"] ?? "unclear"),
			predicate,
			evidence,
			confidence: Math.min(Number(requirement["confidence"] ?? 0), 0.8),
			signals: ["model", "grounded_quote"],
		}));
	}
	if (dropped) warnings.push(`${dropped} model requirements were omitted because they were unsafe or ungrounded`);
	return [candidates, warnings];
};

const normalizeModelPredicate = (predicate: Record<string, unknown>): Record<string, unknown> => {
	const vocabulary = loadVocabulary();
	const criteria = Array.isArray(predicate["criteria"]) ? predicate["criteria"] as Array<Record<string, unknown>> : [];
	for (const criterion of criteria) {
		const name = criterion["canonicalName"];
		if (criterion["type"] === "skill" && typeof name === "string") {
			criterion["canonicalName"] = vocabulary.phraseToCanonical.get(name.toLowerCase()) ?? name;
		}
	}
	return { ...predicate, criteria };
};

const modelPredicateSupported = (predicate: Record<string, unknown>, evidence: readonly Record<string, unknown>[]): boolean => {
	const evidenceText = evidence.map((item) => String(item["quote"] ?? "")).join(" ");
	if (PROHIBITED_PATTERN.test(evidenceText)) return false;
	const evidenceSkills = mentionedSkills(evidenceText);
	const criteria = predicate["criteria"];
	if (!Array.isArray(criteria)) return false;
	for (const raw of criteria) {
		if (typeof raw !== "object" || raw === null) return false;
		const criterion = raw as Record<string, unknown>;
		const type = String(criterion["type"] ?? "other");
		if (type === "skill") {
			const name = String(criterion["canonicalName"] ?? "").trim();
			if (!evidenceSkills.has(name) && !evidenceText.toLowerCase().includes(name.toLowerCase())) return false;
		} else if (type === "experience") {
			if (typeof criterion["minimumMonths"] !== "number" || experienceMonths(evidenceText) !== criterion["minimumMonths"]) return false;
			const subjects = criterion["subjects"];
			if (Array.isArray(subjects) && subjects.some((subject) => !evidenceSkills.has(String(subject)) && !evidenceText.toLowerCase().includes(String(subject).toLowerCase()))) return false;
		} else if (type === "education") {
			if (String(criterion["minimumLevel"] ?? "") !== (educationLevel(evidenceText) ?? "")) return false;
		} else if (type === "certification") {
			const name = String(criterion["canonicalName"] ?? "").trim();
			if (!name || !evidenceText.toLowerCase().includes(name.toLowerCase())) return false;
		}
	}
	return true;
};

const deduplicate = (candidates: readonly Record<string, unknown>[], warnings: string[]): Array<Record<string, unknown>> => {
	const merged = new Map<string, Record<string, unknown>>();
	const thresholds = new Map<string, Set<number>>();
	for (const candidate of [...candidates].sort((a, b) => Number(b["confidence"]) - Number(a["confidence"]))) {
		const key = predicateKey(candidate["predicate"] as Record<string, unknown>, candidate);
		const existing = merged.get(key);
		if (existing) {
			existing["evidence"] = mergeEvidence(existing["evidence"], candidate["evidence"]);
			existing["signals"] = [...new Set([...(existing["signals"] as string[]), ...(candidate["signals"] as string[])])].sort();
			existing["confidence"] = Math.min(0.98, Number(existing["confidence"]) + 0.08);
			continue;
		}
		merged.set(key, { ...candidate });
		for (const criterion of ((candidate["predicate"] as Record<string, unknown>)["criteria"] as Array<Record<string, unknown>>)) {
			if (criterion["type"] !== "experience") continue;
			const subjects = JSON.stringify([...((criterion["subjects"] as string[] | null) ?? [])].sort());
			if (typeof criterion["minimumMonths"] === "number") {
				const set = thresholds.get(`experience:${subjects}`) ?? new Set<number>();
				set.add(criterion["minimumMonths"]);
				thresholds.set(`experience:${subjects}`, set);
			}
		}
	}
	for (const [key, values] of thresholds) {
		if (values.size > 1) {
			const subjects = JSON.parse(key.slice("experience:".length)) as string[];
			warnings.push(`Conflicting thresholds found for ${subjects.length ? subjects.join(", ") : "general experience"}; recruiter review is required`);
		}
	}
	return [...merged.values()];
};

const predicateKey = (predicate: Record<string, unknown>, candidate: Record<string, unknown>): string => {
	const criteria = predicate["criteria"] as Array<Record<string, unknown>>;
	if (criteria.every((item) => item["type"] === "other")) return `text:${String(candidate["normalizedText"]).toLowerCase()}`;
	return `predicate:${JSON.stringify(predicate)}`;
};

const mergeEvidence = (left: unknown, right: unknown): Array<Record<string, unknown>> => {
	const entries = [...(left as Array<Record<string, unknown>>), ...(right as Array<Record<string, unknown>>)];
	const seen = new Set<string>();
	const merged: Array<Record<string, unknown>> = [];
	for (const entry of entries) {
		const key = `${String(entry["blockId"])}:${Number(entry["startOffset"])}:${Number(entry["endOffset"])}`;
		if (!seen.has(key)) {
			seen.add(key);
			merged.push(entry);
		}
	}
	return merged;
};

const finalizeCandidate = (candidate: Record<string, unknown>): Record<string, unknown> => {
	const evidence = candidate["evidence"] as Array<Record<string, unknown>>;
	const identity = {
		text: candidate["normalizedText"],
		predicate: candidate["predicate"],
		source: evidence.map((entry) => [entry["blockId"], entry["startOffset"], entry["endOffset"]]),
	};
	const digest = createHash("sha256").update(JSON.stringify(identity), "utf8").digest("hex").slice(0, 16);
	return { stableId: `requirement-${digest}`, ...candidate };
};

export const educationLevel = (text: string): string | null => {
	const lowered = text.toLowerCase();
	for (const [level, phrases] of Object.entries(DEGREE_LEVELS)) {
		if (phrases.some((phrase) => lowered.includes(phrase))) return level;
	}
	return null;
};

export const experienceMonths = (text: string): number | null => {
	const digits = YEARS_PATTERN.exec(text);
	if (digits?.[1]) return Number(digits[1]) * 12;
	const words = WORD_YEARS_PATTERN.exec(text);
	if (words?.[1]) return (NUMBER_WORDS[words[1].toLowerCase()] ?? 0) * 12 || null;
	return null;
};

export const normalizedStatement = (text: string): string =>
	text.normalize("NFKC").split(/\s+/).join(" ").trim().replace(/ ;$/, "").replace(/;$/, "");

const uniqueStrings = (values: readonly string[]): string[] => {
	const seen = new Set<string>();
	const result: string[] = [];
	for (const value of values) {
		if (!seen.has(value.toLowerCase())) {
			seen.add(value.toLowerCase());
			result.push(value);
		}
	}
	return result;
};

export type { ModelExtraction };
