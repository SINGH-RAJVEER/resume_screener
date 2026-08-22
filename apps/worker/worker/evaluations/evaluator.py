
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from ..documents.vocabulary import mentioned_skills


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
	assessments = [assess_requirement(requirement, skills) for requirement in requirement_list]
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
	requirement: Mapping[str, Any], skills: Mapping[str, list[str]]
) -> Assessment:
	required_skills = mentioned_skills(str(requirement["normalized_text"]))
	if not required_skills:
		return Assessment(
			str(requirement["id"]), "unknown", 0, "No deterministic criterion match.", []
		)
	matched = [(skill, skills[skill]) for skill in sorted(required_skills) if skills.get(skill)]
	evidence = [
		{"blockId": block_id, "quote": skill}
		for skill, block_ids in matched
		for block_id in block_ids
	]
	if len(matched) == len(required_skills):
		return Assessment(
			str(requirement["id"]), "met", 1, "All explicit skill evidence found.", evidence
		)
	if matched:
		return Assessment(
			str(requirement["id"]), "partial", 1, "Some explicit skill evidence found.", evidence
		)
	return Assessment(
		str(requirement["id"]), "not_met", 1, "Explicit required skill is not documented.", []
	)


def outcome_value(outcome: str) -> float:
	return {"met": 1, "partial": 0.5, "not_met": 0}[outcome]
