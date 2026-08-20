import json

import pytest
from pydantic import ValidationError

from app.extraction_schemas import (
	AssessmentOutcome,
	ConfirmedJobRequirement,
	EvidenceReference,
	RequirementAssessment,
	ResumeFacts,
)


def evidence(block_id: str = "p1-b2") -> dict[str, object]:
	return {"blockId": block_id, "quote": "Built APIs in Python."}


def test_resume_facts_accepts_evidence_backed_extraction() -> None:
	facts = ResumeFacts.model_validate(
		{
			"skills": [
				{
					"canonicalName": "Python",
					"sourceText": "Built APIs in Python.",
					"evidence": [evidence()],
				}
			],
			"employment": [],
			"projects": [],
			"education": [],
			"certifications": [],
			"warnings": [],
		}
	)

	assert facts.skills[0].canonical_name == "Python"
	assert facts.skills[0].evidence[0].block_id == "p1-b2"


def test_extraction_schemas_reject_unknown_fields_and_coercion() -> None:
	with pytest.raises(ValidationError):
		EvidenceReference.model_validate(
			{"blockId": "p1-b2", "quote": "Evidence", "unexpected": True}
		)

	with pytest.raises(ValidationError):
		RequirementAssessment.model_validate(
			{
				"requirementId": "req-1",
				"outcome": "met",
				"confidence": "0.9",
				"reasoning": "The resume explicitly names the skill.",
				"evidence": [evidence()],
			}
		)


def test_confirmed_requirement_uses_the_default_weight_for_its_kind() -> None:
	requirement = ConfirmedJobRequirement.model_validate_json(
		json.dumps(
			{
				"stableId": "python",
				"category": "skill",
				"normalizedText": "Python experience",
				"suggestedImportance": "high",
				"sourceEvidence": [evidence()],
				"kind": "required",
			}
		)
	)

	assert requirement.weight == 2


def test_confirmed_assessment_outcomes_require_evidence() -> None:
	with pytest.raises(ValidationError, match="confirmed outcomes require evidence"):
		RequirementAssessment.model_validate(
			{
				"requirementId": "req-1",
				"outcome": AssessmentOutcome.MET,
				"confidence": 0.2,
				"reasoning": "The resume explicitly names the skill.",
			}
		)


def test_unknown_requirement_assessment_can_cite_ambiguous_evidence() -> None:
	assessment = RequirementAssessment.model_validate(
		{
			"requirementId": "req-1",
			"outcome": AssessmentOutcome.UNKNOWN,
			"confidence": 0.2,
			"reasoning": "The resume does not establish whether this experience is relevant.",
			"evidence": [evidence()],
		}
	)

	assert assessment.outcome is AssessmentOutcome.UNKNOWN
