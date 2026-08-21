from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast


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
	raw_skills = cast(list[Mapping[str, Any]], normalized_facts.get("skills", []))
	skills = {
		str(skill["canonicalName"]): [str(block_id) for block_id in skill["evidenceBlockIds"]]
		for skill in raw_skills
	}
	assessments = [assess_requirement(requirement, skills) for requirement in requirements]
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
	return EvaluationResult(assessments, score, coverage, eligibility)


def assess_requirement(
	requirement: Mapping[str, Any], skills: Mapping[str, list[str]]
) -> Assessment:
	text = str(requirement["normalized_text"]).casefold()
	matched = [(skill, blocks) for skill, blocks in skills.items() if skill.casefold() in text]
	if not matched:
		return Assessment(
			str(requirement["id"]), "unknown", 0, "No deterministic criterion match.", []
		)
	evidence = [
		{"blockId": block_id, "quote": skill}
		for skill, block_ids in matched
		for block_id in block_ids
	]
	if evidence:
		return Assessment(
			str(requirement["id"]), "met", 1, "Explicit skill evidence found.", evidence
		)
	return Assessment(
		str(requirement["id"]), "not_met", 1, "Required skill is not documented.", []
	)


def outcome_value(outcome: str) -> float:
	return {"met": 1, "partial": 0.5, "not_met": 0}[outcome]
