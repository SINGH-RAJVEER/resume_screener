
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
			outcome = "partial" if outcome == "not_met" else assessment.outcome
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
		"not_met",
		1,
		"Explicit required skill is not documented.",
		[],
	)


def assess_experience(
	requirement_id: str, needed_years: int, facts: Mapping[str, Any]
) -> Assessment:
	total_months = employment_months(facts.get("employment"))
	if total_months is None:
		return Assessment(
			requirement_id,
			"unknown",
			0,
			"No dated employment documented to compute experience.",
			[],
		)
	needed_months = needed_years * 12
	if total_months >= needed_months:
		outcome = "met"
	elif total_months >= needed_months // 2:
		outcome = "partial"
	else:
		outcome = "not_met"
	years_text = f"{total_months // 12}y {total_months % 12}m"
	reasoning = (
		f"Dated employment totals {years_text} against {needed_years} years required."
	)
	return Assessment(requirement_id, outcome, 1, reasoning, [])


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


def outcome_value(outcome: str) -> float:
	return {"met": 1, "partial": 0.5, "not_met": 0}[outcome]
