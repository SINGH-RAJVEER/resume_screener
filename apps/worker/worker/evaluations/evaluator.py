
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from ..documents.vocabulary import mentioned_skills

YEARS_PATTERN = re.compile(r"(\d+)\s*\+?\s*years?", re.IGNORECASE)

EDUCATION_LEVELS: dict[str, tuple[str, ...]] = {
	"doctorate": ("phd", "doctorate", "d.litt", "dphil"),
	"master": ("master", "m.tech", "mtech", "m.sc", "msc", "mba", "m.a.", "m.a"),
	"bachelor": (
		"bachelor",
		"b.tech",
		"btech",
		"b.sc",
		"bsc",
		"b.e.",
		"b.a.",
	),
}


@dataclass(frozen=True)
class Assessment:
	requirement_id: str
	outcome: str
	confidence: float
	reasoning: str
	evidence: list[dict[str, str]]


@dataclass(frozen=True)
class EvaluationResult:
	assessments: list[Assessment]
	score: int | None
	evidence_coverage: int
	eligibility: str


def evaluate(
	normalized_facts: Mapping[str, Any], requirements: Iterable[Mapping[str, Any]]
) -> EvaluationResult:
	requirement_list = list(requirements)
	raw_skills = cast(list[Mapping[str, Any]], normalized_facts.get("skills", []))
	skills = {
		str(skill["canonicalName"]): [str(block_id) for block_id in skill["evidenceBlockIds"]]
		for skill in raw_skills
	}
	assessments = [
		assess_requirement(requirement, skills, normalized_facts)
		for requirement in requirement_list
	]
	return summarize(assessments, requirement_list)


def summarize(
	assessments: Sequence[Assessment], requirements: Sequence[Mapping[str, Any]]
) -> EvaluationResult:
	scored = [
		(assessment, requirement)
		for assessment, requirement in zip(assessments, requirements, strict=True)
		if str(requirement["kind"]) not in {"ignored", "hard_gate"}
	]
	known = [
		(assessment, requirement)
		for assessment, requirement in scored
		if assessment.outcome != "unknown"
	]
	denominator = sum(int(requirement["weight"]) for _, requirement in known)
	numerator = sum(
		int(requirement["weight"]) * outcome_value(assessment.outcome)
		for assessment, requirement in known
	)
	score = round(100 * numerator / denominator) if denominator else None
	coverage = round(100 * len(known) / len(scored)) if scored else 100
	hard_gates = [
		assessment
		for assessment, requirement in zip(assessments, requirements, strict=True)
		if str(requirement["kind"]) == "hard_gate"
	]
	eligibility = (
		"not_eligible"
		if any(assessment.outcome == "not_met" for assessment in hard_gates)
		else "needs_review"
		if any(assessment.outcome in {"partial", "unknown"} for assessment in hard_gates)
		else "eligible"
	)
	return EvaluationResult(list(assessments), score, coverage, eligibility)


def refine_assessments(
	deterministic: Sequence[Assessment],
	model_assessments: Sequence[Mapping[str, object]],
	requirements: Sequence[Mapping[str, Any]],
) -> list[Assessment]:
	"""Prefer model outcomes while never lowering evidenced deterministic matches."""
	by_requirement = {str(item.get("requirementId")): item for item in model_assessments}
	refined: list[Assessment] = []
	for assessment, requirement in zip(deterministic, requirements, strict=True):
		model = by_requirement.get(str(requirement["id"]))
		if model is None:
			refined.append(assessment)
			continue
		outcome = str(model.get("outcome", "unknown"))
		if assessment.outcome == "met" and outcome != "met":
			# Deterministic evidence proves the claim; a model cannot erase it.
			outcome = assessment.outcome
		reasoning = str(model.get("reasoning", "")) or assessment.reasoning
		evidence = [
			cast(dict[str, str], entry)
			for entry in cast(list[object], model.get("evidence") or [])
			if isinstance(entry, dict)
		] or assessment.evidence
		raw_confidence = model.get("confidence", 0.0)
		confidence = max(0.0, min(float(cast(int | float, raw_confidence)), 1.0))
		refined.append(
			Assessment(
				assessment.requirement_id,
				outcome,
				confidence,
				reasoning,
				evidence,
			)
		)
	return refined


def assess_requirement(
	requirement: Mapping[str, Any],
	skills: Mapping[str, list[str]],
	facts: Mapping[str, Any] | None = None,
) -> Assessment:
	if str(requirement.get("assessability", "resume_evidence")) != "resume_evidence":
		return Assessment(
			str(requirement["id"]),
			"unknown",
			0,
			"This requirement cannot be assessed from resume evidence.",
			[],
		)
	predicate = requirement.get("predicate")
	predicate_map: Mapping[str, object]
	if isinstance(predicate, Mapping):
		predicate_map = cast(Mapping[str, object], predicate)
	else:
		predicate_map = {}
	if predicate_map.get("criteria"):
		return assess_predicate(
			str(requirement["id"]),
			predicate_map,
			skills,
			facts or {},
		)
	text = str(requirement["normalized_text"])
	required_skills = mentioned_skills(text)
	if required_skills:
		return assess_skills(str(requirement["id"]), text, required_skills, skills)
	facts = facts or {}
	years = YEARS_PATTERN.search(text)
	if years is not None:
		return assess_experience(
			str(requirement["id"]), int(years.group(1)), facts
		)
	cert = find_certification(text, facts)
	if cert is not None:
		return Assessment(
			str(requirement["id"]),
			"met",
			1,
			"Documented certification matches the requirement.",
			cert[1],
		)
	level = find_education_level(text, facts)
	if level is not None:
		outcome, reasoning = level
		return Assessment(str(requirement["id"]), outcome, 1, reasoning, [])
	return Assessment(
		str(requirement["id"]),
		"unknown",
		0,
		"No deterministic criterion match.",
		[],
	)


def assess_predicate(
	requirement_id: str,
	predicate: Mapping[str, object],
	skills: Mapping[str, list[str]],
	facts: Mapping[str, Any],
) -> Assessment:
	raw_criteria = predicate.get("criteria")
	if not isinstance(raw_criteria, list) or not raw_criteria:
		return Assessment(requirement_id, "unknown", 0, "Requirement predicate is invalid.", [])
	criteria = [
		assess_criterion(requirement_id, cast(Mapping[str, object], criterion), skills, facts)
		for criterion in cast(list[object], raw_criteria)
		if isinstance(criterion, Mapping)
	]
	if not criteria:
		return Assessment(requirement_id, "unknown", 0, "Requirement predicate is invalid.", [])
	operator = str(predicate.get("operator", "all_of"))
	return combine_criterion_assessments(requirement_id, operator, criteria)


def assess_criterion(
	requirement_id: str,
	criterion: Mapping[str, object],
	skills: Mapping[str, list[str]],
	facts: Mapping[str, Any],
) -> Assessment:
	criterion_type = str(criterion.get("type", "other"))
	if criterion_type == "skill":
		name = str(criterion.get("canonicalName") or "").strip()
		block_ids = skills.get(name, [])
		if block_ids:
			return Assessment(
				requirement_id,
				"met",
				1,
				f"Documented evidence names {name}.",
				[{"blockId": block_id, "quote": name} for block_id in block_ids],
			)
		return Assessment(
			requirement_id,
			"unknown",
			0,
			f"The resume does not establish whether the candidate has {name} experience.",
			[],
		)
	if criterion_type == "experience":
		subjects = criterion.get("subjects")
		if isinstance(subjects, list) and subjects:
			return Assessment(
				requirement_id,
				"unknown",
				0,
				"The resume does not establish a dated duration for the required subject.",
				[],
			)
		minimum_months = criterion.get("minimumMonths")
		if not isinstance(minimum_months, int):
			return Assessment(
				requirement_id,
				"unknown",
				0,
				"Experience threshold is invalid.",
				[],
			)
		return assess_experience_months(requirement_id, minimum_months, facts)
	if criterion_type == "education":
		level = str(criterion.get("minimumLevel") or "").strip()
		return assess_education_criterion(requirement_id, level, facts)
	if criterion_type == "certification":
		name = str(criterion.get("canonicalName") or "").strip()
		return assess_certification_criterion(requirement_id, name, facts)
	return Assessment(
		requirement_id,
		"unknown",
		0,
		"This criterion needs evidence review.",
		[],
	)


def combine_criterion_assessments(
	requirement_id: str,
	operator: str,
	criteria: Sequence[Assessment],
) -> Assessment:
	outcomes = [criterion.outcome for criterion in criteria]
	evidence = [item for criterion in criteria for item in criterion.evidence]
	if operator == "any_of":
		if "met" in outcomes:
			outcome = "met"
		elif "partial" in outcomes:
			outcome = "partial"
		elif outcomes and all(value == "not_met" for value in outcomes):
			outcome = "not_met"
		else:
			outcome = "unknown"
		reasoning = (
			"At least one allowed path is documented."
			if outcome == "met"
			else "No allowed path can be established from the resume."
		)
	else:
		if outcomes and all(value == "met" for value in outcomes):
			outcome = "met"
		elif "not_met" in outcomes:
			outcome = "not_met"
		elif any(value in {"met", "partial"} for value in outcomes):
			outcome = "partial"
		else:
			outcome = "unknown"
		reasoning = (
			"All required parts are documented."
			if outcome == "met"
			else "Only part of the requirement is documented."
			if outcome == "partial"
			else "The complete requirement cannot be established from the resume."
		)
	confidence = min((criterion.confidence for criterion in criteria), default=0)
	return Assessment(requirement_id, outcome, confidence, reasoning, evidence)


def assess_skills(
	requirement_id: str,
	text: str,
	required_skills: set[str],
	skills: Mapping[str, list[str]],
) -> Assessment:
	matched = [(skill, skills[skill]) for skill in sorted(required_skills) if skills.get(skill)]
	evidence = [
		{"blockId": block_id, "quote": skill}
		for skill, block_ids in matched
		for block_id in block_ids
	]
	if len(matched) == len(required_skills):
		return Assessment(
			requirement_id, "met", 1, "All explicit skill evidence found.", evidence
		)
	if matched:
		return Assessment(
			requirement_id,
			"partial",
			1,
			"Some explicit skill evidence found.",
			evidence,
		)
	return Assessment(
		requirement_id,
		"unknown",
		0,
		"The resume does not establish whether the required skill is held.",
		[],
	)


def assess_experience(
	requirement_id: str, needed_years: int, facts: Mapping[str, Any]
) -> Assessment:
	return assess_experience_months(requirement_id, needed_years * 12, facts)


def assess_experience_months(
	requirement_id: str, needed_months: int, facts: Mapping[str, Any]
) -> Assessment:
	total_months = employment_months(facts.get("employment"))
	if total_months is None:
		return Assessment(
			requirement_id,
			"unknown",
			0,
			"No dated employment is documented to compute experience.",
			[],
		)
	if total_months >= needed_months:
		outcome = "met"
	elif total_months >= needed_months // 2:
		outcome = "partial"
	else:
		outcome = "unknown"
	years_text = f"{total_months // 12}y {total_months % 12}m"
	needed_years = needed_months / 12
	reasoning = (
		f"Documented employment totals {years_text} against {needed_years:g} years required."
	)
	return Assessment(requirement_id, outcome, 1 if outcome != "unknown" else 0, reasoning, [])


def employment_months(entries: object) -> int | None:
	items = cast(list[object], entries) if isinstance(entries, list) else []
	intervals: list[tuple[int, int]] = []
	now = datetime.now(UTC)
	now_month = now.year * 12 + now.month
	for item in items:
		if not isinstance(item, Mapping):
			continue
		entry = cast(Mapping[str, Any], item)
		start = month_index(entry.get("startDate"))
		end = month_index(entry.get("endDate"))
		if end is None and entry.get("isCurrent") is True:
			end = now_month
		if start is None or end is None or end < start:
			continue
		intervals.append((start, end))
	if not intervals:
		return None
	intervals.sort()
	total = 0
	current_start, current_end = intervals[0]
	for start, end in intervals[1:]:
		if start <= current_end:
			current_end = max(current_end, end)
			continue
		total += current_end - current_start
		current_start, current_end = start, end
	total += current_end - current_start
	return total


def month_index(value: object) -> int | None:
	if not isinstance(value, str):
		return None
	parts = value.split("-")
	try:
		year = int(parts[0])
		month = int(parts[1]) if len(parts) > 1 else 1
	except ValueError:
		return None
	if not 1 <= month <= 12:
		return None
	return year * 12 + month


def find_certification(
	text: str, facts: Mapping[str, Any]
) -> tuple[str, list[dict[str, str]]] | None:
	certifications = facts.get("certifications")
	if not isinstance(certifications, list):
		return None
	lowered = text.casefold()
	for item in cast(list[object], certifications):
		if not isinstance(item, Mapping):
			continue
		entry = cast(Mapping[str, Any], item)
		name = str(entry.get("name") or "").strip()
		if len(name) < 4:
			continue
		if name.casefold() in lowered or any(
			len(token) >= 3 and f" {token} " in f" {lowered} ".replace("(", " ").replace(")", " ")
			for token in name.casefold().split()
		):
			return name, [{"blockId": "facts", "quote": name}]
	return None


def find_education_level(
	text: str, facts: Mapping[str, Any]
) -> tuple[str, str] | None:
	education = facts.get("education")
	if not isinstance(education, list) or not education:
		return None
	lowered = text.casefold()
	requested = [
		level for level, words in EDUCATION_LEVELS.items() if any(w in lowered for w in words)
	]
	if not requested and "degree" not in lowered:
		return None
	documented_levels: set[str] = set()
	for item in cast(list[object], education):
		if not isinstance(item, Mapping):
			continue
		entry = cast(Mapping[str, Any], item)
		degree = str(entry.get("degree") or "").casefold()
		if not degree:
			continue
		for level, words in EDUCATION_LEVELS.items():
			if any(word in degree for word in words):
				documented_levels.add(level)
	if requested:
		if any(level in documented_levels for level in requested):
			return "met", "Documented education includes the requested level."
		if documented_levels:
			return (
				"partial",
				"Education is documented but at a different level than requested.",
			)
		return "not_met", "No matching education level is documented."
	return "met", "A degree is documented."


def assess_education_criterion(
	requirement_id: str,
	minimum_level: str,
	facts: Mapping[str, Any],
) -> Assessment:
	ranks = {"bachelor": 1, "master": 2, "doctorate": 3}
	requested_rank = ranks.get(minimum_level)
	if requested_rank is None:
		return Assessment(requirement_id, "unknown", 0, "Education level is unclear.", [])
	documented = documented_education_levels(facts)
	if not documented:
		return Assessment(
			requirement_id,
			"unknown",
			0,
			"No education level is documented.",
			[],
		)
	if max(ranks[level] for level in documented) >= requested_rank:
		return Assessment(
			requirement_id,
			"met",
			1,
			"Documented education meets or exceeds the requested level.",
			[],
		)
	return Assessment(
		requirement_id,
		"partial",
		1,
		"Education is documented below the requested level.",
		[],
	)


def documented_education_levels(facts: Mapping[str, Any]) -> set[str]:
	education = facts.get("education")
	if not isinstance(education, list):
		return set()
	levels: set[str] = set()
	for item in cast(list[object], education):
		if not isinstance(item, Mapping):
			continue
		degree = str(cast(Mapping[str, object], item).get("degree") or "").casefold()
		for level, words in EDUCATION_LEVELS.items():
			if any(word in degree for word in words):
				levels.add(level)
	return levels


def assess_certification_criterion(
	requirement_id: str,
	name: str,
	facts: Mapping[str, Any],
) -> Assessment:
	certifications = facts.get("certifications")
	if not isinstance(certifications, list):
		return Assessment(requirement_id, "unknown", 0, "No certifications are documented.", [])
	normalized_name = normalize_credential_name(name)
	for item in cast(list[object], certifications):
		if not isinstance(item, Mapping):
			continue
		documented_name = str(cast(Mapping[str, object], item).get("name") or "")
		if normalized_name and normalize_credential_name(documented_name) == normalized_name:
			return Assessment(
				requirement_id,
				"met",
				1,
				"The required certification is documented.",
				[{"blockId": "facts", "quote": documented_name}],
			)
	return Assessment(
		requirement_id,
		"unknown",
		0,
		"The resume does not establish whether the certification is held.",
		[],
	)


def normalize_credential_name(value: str) -> str:
	return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def outcome_value(outcome: str) -> float:
	return {"met": 1, "partial": 0.5, "not_met": 0}[outcome]
