from typing import SupportsFloat, cast

from worker.evaluations.evaluator import Assessment, refine_assessments, summarize


def requirement(kind: str = "required", weight: int = 2) -> dict[str, object]:
	return {"id": "req-1", "kind": kind, "weight": weight, "normalized_text": "Python"}


def deterministic(outcome: str) -> list[Assessment]:
	return [Assessment("req-1", outcome, 1.0, "deterministic", [])]


def model_outcome(
	outcome: str,
	confidence: float = 0.8,
	evidence: list[dict[str, object]] | None = None,
	reasoning: str = "model reasoning",
) -> list[dict[str, object]]:
	return [
		{
			"requirementId": "req-1",
			"outcome": outcome,
			"confidence": confidence,
			"reasoning": reasoning,
			"evidence": evidence or [],
		}
	]


def test_model_can_confirm_unknown_requirements_with_evidence() -> None:
	refined = refine_assessments(
		deterministic("unknown"),
		model_outcome("met", evidence=[{"blockId": "p1-b1", "quote": "built in Python"}]),
		[requirement()],
	)
	assert refined[0].outcome == "met"
	assert refined[0].reasoning == "model reasoning"
	result = summarize(refined, [requirement()])
	assert result.score == 100


def test_model_cannot_erase_deterministic_evidence() -> None:
	refined = refine_assessments(
		deterministic("met"),
		model_outcome("not_met"),
		[requirement()],
	)
	assert refined[0].outcome == "met"


def test_unsupported_confirmation_degrades_to_unknown() -> None:
	from worker.extraction.extractor import validate_assessments

	validated = validate_assessments(
		{"assessments": [
			{
				"requirementId": "req-1",
				"outcome": "not_met",
				"confidence": 0.9,
				"reasoning": "absent",
				"evidence": [],
			}
		]},
		{"req-1"},
		{"p1-b1"},
	)
	assert validated[0]["outcome"] == "unknown"
	assert float(cast("SupportsFloat", validated[0]["confidence"])) <= 0.5


def test_summarize_hard_gate_eligibility() -> None:
	requirements = [dict(requirement(), kind="hard_gate")]
	failing = [Assessment("req-1", "not_met", 1.0, "missing", [])]
	assert summarize(failing, requirements).eligibility == "not_eligible"
	uncertain = [Assessment("req-1", "unknown", 0.0, "no data", [])]
	assert summarize(uncertain, requirements).eligibility == "needs_review"
