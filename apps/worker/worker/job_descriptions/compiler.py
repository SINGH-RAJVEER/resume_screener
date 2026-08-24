import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import blake2b
from typing import cast

from ..documents.vocabulary import load_vocabulary, mentioned_skills
from .schemas import (
	JOB_REQUIREMENTS_COMPILER_VERSION,
	JOB_REQUIREMENTS_PROMPT_VERSION,
	JOB_REQUIREMENTS_SCHEMA_VERSION,
	Assessability,
	CriterionType,
	ModelRequirementExtraction,
	PredicateOperator,
	RequirementCategory,
	SourceModality,
	SuggestedKind,
)

MAX_DRAFT_REQUIREMENTS = 50

HEADING_SECTIONS = {
	"requirements": "requirements",
	"qualifications": "requirements",
	"minimum qualifications": "requirements",
	"what you bring": "requirements",
	"what we are looking for": "requirements",
	"what we're looking for": "requirements",
	"preferred qualifications": "preferred",
	"preferred skills": "preferred",
	"nice to have": "preferred",
	"nice-to-have": "preferred",
	"bonus points": "preferred",
	"responsibilities": "responsibilities",
	"what you will do": "responsibilities",
	"what you'll do": "responsibilities",
	"about us": "about",
	"about the company": "about",
	"benefits": "benefits",
	"what we offer": "benefits",
	"equal opportunity": "legal",
	"how to apply": "application",
}

REQUIRED_CUE = re.compile(
	r"\b(must|required|minimum|need to|needs to|shall|essential)\b",
	re.IGNORECASE,
)
PREFERRED_CUE = re.compile(
	r"\b(preferred|nice[ -]to[ -]have|bonus|plus|desirable|ideally)\b",
	re.IGNORECASE,
)
YEARS_PATTERN = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE)
DEGREE_LEVELS = {
	"doctorate": ("phd", "doctorate", "doctoral", "dphil"),
	"master": ("master", "mba", "mtech", "m.tech", "msc", "m.sc"),
	"bachelor": ("bachelor", "undergraduate degree", "btech", "b.tech", "bsc", "b.sc"),
}
PROHIBITED_PATTERN = re.compile(
	r"\b(age|gender|sex|race|ethnicity|religion|marital status|pregnan(?:t|cy)|disability)\b",
	re.IGNORECASE,
)
ATTESTATION_PATTERNS = {
	RequirementCategory.WORK_AUTHORIZATION: re.compile(
		r"\b(work authorization|authorized to work|visa sponsorship|right to work)\b",
		re.IGNORECASE,
	),
	RequirementCategory.LOCATION: re.compile(
		r"\b(relocat(?:e|ion)|reside in|based in|commutable distance)\b",
		re.IGNORECASE,
	),
	RequirementCategory.SCHEDULE: re.compile(
		r"\b(night shift|weekends?|on[ -]call|travel|time zone|working hours)\b",
		re.IGNORECASE,
	),
}
SOFT_SKILL_PATTERN = re.compile(
	r"\b(communication|team player|self[ -]starter|leadership style|interpersonal)\b",
	re.IGNORECASE,
)
CERTIFICATION_PATTERN = re.compile(
	r"\b(certification|certified|licen[cs]e|credential)\b",
	re.IGNORECASE,
)
BULLET_PATTERN = re.compile(r"^\s*(?:[-*•▪◦]+|\d+[.)])\s+")


@dataclass(frozen=True)
class JobBlock:
	id: str
	text: str
	section: str
	start_offset: int
	end_offset: int
	was_bullet: bool


def source_blocks(source_text: str) -> list[JobBlock]:
	blocks: list[JobBlock] = []
	section = "unknown"
	offset = 0
	for raw_line in source_text.splitlines(keepends=True):
		line = raw_line.rstrip("\r\n")
		stripped = line.strip()
		line_start = offset
		offset += len(raw_line)
		if not stripped:
			continue
		heading_key = re.sub(r"[:\s]+$", "", stripped).casefold()
		if heading_key in HEADING_SECTIONS and len(stripped) <= 80:
			section = HEADING_SECTIONS[heading_key]
			continue
		bullet = BULLET_PATTERN.match(line)
		content_start = bullet.end() if bullet else len(line) - len(line.lstrip())
		content = line[content_start:].strip()
		if len(content) < 3:
			continue
		local_start = line.find(content, content_start)
		start = line_start + local_start
		blocks.append(
			JobBlock(
				id=f"jd-b{len(blocks) + 1}",
				text=content,
				section=section,
				start_offset=start,
				end_offset=start + len(content),
				was_bullet=bullet is not None,
			)
		)
	if not source_text.endswith(("\n", "\r")) and offset < len(source_text):
		offset = len(source_text)
	return blocks


def blocks_for_model(blocks: Sequence[JobBlock]) -> list[dict[str, object]]:
	return [
		{"id": block.id, "section": block.section, "text": block.text}
		for block in blocks
	]


def compile_job_description(
	source_text: str,
	model_output: Mapping[str, object] | None = None,
	*,
	degraded: bool = False,
	degraded_reason: str | None = None,
) -> dict[str, object]:
	blocks = source_blocks(source_text)
	warnings: list[str] = []
	candidates = deterministic_candidates(blocks, warnings)
	if model_output is not None:
		model_candidates, model_warnings = grounded_model_candidates(model_output, blocks)
		warnings.extend(model_warnings)
		candidates.extend(model_candidates)
	requirements = deduplicate(candidates, warnings)[:MAX_DRAFT_REQUIREMENTS]
	if len(candidates) > MAX_DRAFT_REQUIREMENTS:
		warnings.append("Low-confidence requirements were omitted after the review limit")
	if degraded_reason:
		warnings.append(degraded_reason)
	quality_state = "ready" if requirements else "review_required"
	if not requirements:
		warnings.append("No explicit job requirements were found; add criteria manually")
	return {
		"schemaVersion": JOB_REQUIREMENTS_SCHEMA_VERSION,
		"compilerVersion": JOB_REQUIREMENTS_COMPILER_VERSION,
		"promptVersion": JOB_REQUIREMENTS_PROMPT_VERSION,
		"degraded": degraded,
		"qualityState": quality_state,
		"warnings": unique_strings(warnings),
		"requirements": requirements,
	}


def deterministic_candidates(
	blocks: Sequence[JobBlock], warnings: list[str]
) -> list[dict[str, object]]:
	candidates: list[dict[str, object]] = []
	for block in blocks:
		text = normalized_statement(block.text)
		if block.section in {"about", "benefits", "legal", "application"}:
			continue
		if PROHIBITED_PATTERN.search(text):
			warnings.append(f"Potentially prohibited criterion omitted from {block.id}")
			continue
		skills = sorted(mentioned_skills(text), key=str.casefold)
		has_cue = REQUIRED_CUE.search(text) or PREFERRED_CUE.search(text)
		in_requirement_section = block.section in {"requirements", "preferred"}
		if block.section == "responsibilities" and not has_cue:
			continue
		if not in_requirement_section and not has_cue and not (block.was_bullet and skills):
			continue
		candidate = deterministic_candidate(block, text, skills)
		candidates.append(candidate)
	return candidates


def deterministic_candidate(
	block: JobBlock, text: str, skills: Sequence[str]
) -> dict[str, object]:
	suggested_kind, source_modality = infer_importance(block.section, text)
	category, assessability = infer_category_and_assessability(text, skills)
	predicate = infer_predicate(text, skills)
	evidence = [
		{
			"blockId": block.id,
			"quote": block.text,
			"startOffset": block.start_offset,
			"endOffset": block.end_offset,
			"section": block.section,
		}
	]
	signals = ["section"] if block.section in {"requirements", "preferred"} else []
	if skills:
		signals.append("taxonomy")
	if REQUIRED_CUE.search(text) or PREFERRED_CUE.search(text):
		signals.append("language_cue")
	confidence = min(0.92, 0.55 + 0.12 * len(signals))
	return finalize_candidate(
		{
			"normalizedText": text,
			"category": category.value,
			"suggestedKind": suggested_kind.value,
			"suggestedWeight": 2 if suggested_kind is SuggestedKind.REQUIRED else 1,
			"sourceModality": source_modality.value,
			"assessability": assessability.value,
			"predicate": predicate,
			"evidence": evidence,
			"confidence": confidence,
			"signals": signals or ["bullet"],
		}
	)


def infer_importance(section: str, text: str) -> tuple[SuggestedKind, SourceModality]:
	if PREFERRED_CUE.search(text):
		return SuggestedKind.PREFERRED, SourceModality.EXPLICIT_PREFERRED
	if REQUIRED_CUE.search(text):
		return SuggestedKind.REQUIRED, SourceModality.EXPLICIT_REQUIRED
	if section == "preferred":
		return SuggestedKind.PREFERRED, SourceModality.SECTION_PREFERRED
	if section == "requirements":
		return SuggestedKind.REQUIRED, SourceModality.SECTION_REQUIRED
	return SuggestedKind.PREFERRED, SourceModality.UNCLEAR


def infer_category_and_assessability(
	text: str, skills: Sequence[str]
) -> tuple[RequirementCategory, Assessability]:
	for category, pattern in ATTESTATION_PATTERNS.items():
		if pattern.search(text):
			return category, Assessability.CANDIDATE_ATTESTATION
	if SOFT_SKILL_PATTERN.search(text):
		return RequirementCategory.SOFT_SKILL, Assessability.RECRUITER_REVIEW
	if YEARS_PATTERN.search(text):
		return RequirementCategory.EXPERIENCE, Assessability.RESUME_EVIDENCE
	if education_level(text):
		return RequirementCategory.EDUCATION, Assessability.RESUME_EVIDENCE
	if CERTIFICATION_PATTERN.search(text):
		return RequirementCategory.CERTIFICATION, Assessability.RESUME_EVIDENCE
	if skills:
		return RequirementCategory.SKILL, Assessability.RESUME_EVIDENCE
	return RequirementCategory.OTHER, Assessability.UNCLEAR


def infer_predicate(text: str, skills: Sequence[str]) -> dict[str, object]:
	criteria: list[dict[str, object]] = []
	years = YEARS_PATTERN.search(text)
	if years:
		criteria.append(
			{
				"type": CriterionType.EXPERIENCE.value,
				"canonicalName": None,
				"minimumMonths": int(years.group(1)) * 12,
				"minimumLevel": None,
				"subjects": list(skills),
			}
		)
	elif skills:
		for skill in skills:
			criteria.append(
				{
					"type": CriterionType.SKILL.value,
					"canonicalName": skill,
					"minimumMonths": None,
					"minimumLevel": None,
					"subjects": [],
				}
			)
	level = education_level(text)
	if level:
		criteria.append(
			{
				"type": CriterionType.EDUCATION.value,
				"canonicalName": None,
				"minimumMonths": None,
				"minimumLevel": level,
				"subjects": [],
			}
		)
	if CERTIFICATION_PATTERN.search(text) and not criteria:
		criteria.append(
			{
				"type": CriterionType.CERTIFICATION.value,
				"canonicalName": text,
				"minimumMonths": None,
				"minimumLevel": None,
				"subjects": [],
			}
		)
	if not criteria:
		criteria.append(
			{
				"type": CriterionType.OTHER.value,
				"canonicalName": None,
				"minimumMonths": None,
				"minimumLevel": None,
				"subjects": [],
			}
		)
	operator = (
		PredicateOperator.ANY_OF
		if re.search(r"\bor\b", text, re.IGNORECASE)
		else PredicateOperator.ALL_OF
	)
	return {"operator": operator.value, "criteria": criteria}


def grounded_model_candidates(
	model_output: Mapping[str, object], blocks: Sequence[JobBlock]
) -> tuple[list[dict[str, object]], list[str]]:
	try:
		extraction = ModelRequirementExtraction.model_validate(model_output)
	except ValueError:
		return [], ["Model requirement output failed schema validation"]
	by_id = {block.id: block for block in blocks}
	candidates: list[dict[str, object]] = []
	dropped = 0
	for requirement in extraction.requirements:
		evidence: list[dict[str, object]] = []
		for citation in requirement.evidence:
			block = by_id.get(citation.block_id)
			if block is None:
				continue
			local_start = block.text.find(citation.quote)
			if local_start < 0:
				continue
			evidence.append(
				{
					"blockId": block.id,
					"quote": citation.quote,
					"startOffset": block.start_offset + local_start,
					"endOffset": block.start_offset + local_start + len(citation.quote),
					"section": block.section,
				}
			)
		if not evidence:
			dropped += 1
			continue
		if requirement.assessability is Assessability.PROHIBITED:
			dropped += 1
			continue
		predicate = normalize_model_predicate(
			requirement.predicate.model_dump(by_alias=True)
		)
		kind = requirement.suggested_kind
		candidate = finalize_candidate(
			{
				"normalizedText": normalized_statement(requirement.normalized_text),
				"category": requirement.category.value,
				"suggestedKind": kind.value,
				"suggestedWeight": 2 if kind is SuggestedKind.REQUIRED else 1,
				"sourceModality": requirement.source_modality.value,
				"assessability": requirement.assessability.value,
				"predicate": predicate,
				"evidence": evidence,
				"confidence": min(float(requirement.confidence), 0.8),
				"signals": ["model", "grounded_quote"],
			}
		)
		candidates.append(candidate)
	warnings = list(extraction.warnings)
	if dropped:
		warnings.append(
			f"{dropped} model requirements were omitted because they were unsafe or ungrounded"
		)
	return candidates, warnings


def normalize_model_predicate(predicate: dict[str, object]) -> dict[str, object]:
	vocabulary = load_vocabulary()
	criteria = cast(list[dict[str, object]], predicate["criteria"])
	for criterion in criteria:
		name = criterion.get("canonicalName")
		if criterion.get("type") == CriterionType.SKILL.value and isinstance(name, str):
			criterion["canonicalName"] = vocabulary.phrase_to_canonical.get(
				name.casefold(), name
			)
	return predicate


def deduplicate(
	candidates: Sequence[dict[str, object]], warnings: list[str]
) -> list[dict[str, object]]:
	merged: dict[str, dict[str, object]] = {}
	thresholds: dict[tuple[str, tuple[str, ...]], set[int]] = {}
	for candidate in sorted(
		candidates,
		key=lambda item: float(cast(int | float, item["confidence"])),
		reverse=True,
	):
		key = predicate_key(cast(dict[str, object], candidate["predicate"]), candidate)
		if key in merged:
			existing = merged[key]
			existing["evidence"] = merge_evidence(existing["evidence"], candidate["evidence"])
			existing["signals"] = sorted(
				set(cast(list[str], existing["signals"]))
				| set(cast(list[str], candidate["signals"]))
			)
			existing["confidence"] = min(
				0.98,
				float(cast(int | float, existing["confidence"])) + 0.08,
			)
			continue
		merged[key] = candidate
		predicate = cast(dict[str, object], candidate["predicate"])
		for criterion in cast(list[dict[str, object]], predicate["criteria"]):
			if criterion.get("type") != CriterionType.EXPERIENCE.value:
				continue
			subjects = tuple(sorted(cast(list[str], criterion.get("subjects") or [])))
			threshold = criterion.get("minimumMonths")
			if isinstance(threshold, int):
				thresholds.setdefault(("experience", subjects), set()).add(threshold)
	for (_, subjects), values in thresholds.items():
		if len(values) > 1:
			label = ", ".join(subjects) if subjects else "general experience"
			warnings.append(
				f"Conflicting thresholds found for {label}; recruiter review is required"
			)
	return list(merged.values())


def predicate_key(predicate: dict[str, object], candidate: Mapping[str, object]) -> str:
	criteria = cast(list[dict[str, object]], predicate["criteria"])
	if all(item.get("type") == CriterionType.OTHER.value for item in criteria):
		return "text:" + str(candidate["normalizedText"]).casefold()
	return "predicate:" + json.dumps(predicate, sort_keys=True, separators=(",", ":"))


def merge_evidence(left: object, right: object) -> list[dict[str, object]]:
	entries = cast(list[dict[str, object]], left) + cast(list[dict[str, object]], right)
	seen: set[tuple[str, int, int]] = set()
	merged: list[dict[str, object]] = []
	for entry in entries:
		key = (
			str(entry["blockId"]),
			int(cast(int, entry["startOffset"])),
			int(cast(int, entry["endOffset"])),
		)
		if key not in seen:
			seen.add(key)
			merged.append(entry)
	return merged


def finalize_candidate(candidate: dict[str, object]) -> dict[str, object]:
	evidence = cast(list[dict[str, object]], candidate["evidence"])
	identity = {
		"text": candidate["normalizedText"],
		"predicate": candidate["predicate"],
		"source": [
			(entry["blockId"], entry["startOffset"], entry["endOffset"])
			for entry in evidence
		],
	}
	digest = blake2b(
		json.dumps(identity, sort_keys=True).encode(),
		digest_size=8,
	).hexdigest()
	return {"stableId": f"requirement-{digest}", **candidate}


def education_level(text: str) -> str | None:
	lowered = text.casefold()
	for level, phrases in DEGREE_LEVELS.items():
		if any(phrase in lowered for phrase in phrases):
			return level
	return None


def normalized_statement(text: str) -> str:
	return " ".join(unicodedata.normalize("NFKC", text).split()).strip(" ;")


def unique_strings(values: Sequence[str]) -> list[str]:
	seen: set[str] = set()
	result: list[str] = []
	for value in values:
		key = value.casefold()
		if key not in seen:
			seen.add(key)
			result.append(value)
	return result
