import pytest

from app.api.routes import (
	EXPORT_COLUMNS,
	contribution_by_index,
	evaluation_skill_names,
	export_row_values,
	hard_gate_outcomes,
	resolve_export_columns,
	resume_quality_payload,
)
from app.core.http import APIError
from app.persistence.models import CandidateRecord, Evaluation, ResumeVersion


def test_outcome_contributions_weight_by_kind_and_exclude_unknowns() -> None:
	contributions = contribution_by_index(
		[
			("met", "required", 2),
			("partial", "preferred", 1),
			("unknown", "required", 2),
			("met", "hard_gate", 2),
			("not_met", "required", 4),
		]
	)

	# Confident weight: required 2 + preferred 1 + required 4 = 7.
	assert contributions == [28.6, 7.1, None, None, 0.0]


def test_contributions_are_none_without_confident_weight() -> None:
	assert contribution_by_index([("unknown", "required", 2)]) == [None]
	assert contribution_by_index([("met", "hard_gate", 2)]) == [None]


def test_hard_gate_outcomes_list_only_gate_requirements() -> None:
	gates = hard_gate_outcomes(
		[
			("met", "required", 2, "Python is required"),
			("not_met", "hard_gate", 2, "Degree is required"),
			("unknown", "hard_gate", 1, "Certification is required"),
		]
	)

	assert gates == [
		{"requirement": "Degree is required", "outcome": "not_met"},
		{"requirement": "Certification is required", "outcome": "unknown"},
	]


def test_evaluation_skill_names_reads_normalized_facts() -> None:
	version = ResumeVersion(
		id="version-1",
		resume_document_id="document-1",
		version=1,
		normalized_facts={
			"skills": [
				{"canonicalName": "Python"},
				{"canonicalName": "Kubernetes"},
				"garbage",
			]
		},
	)

	assert evaluation_skill_names(version) == ["Kubernetes", "Python"]


def test_export_row_values_cover_every_allowed_column() -> None:
	evaluation = Evaluation(
		id="evaluation-1",
		resume_submission_id="submission-1",
		job_version_id="job-version-1",
		resume_version_id="version-1",
		status="complete",
		score=82,
		evidence_coverage=64,
		eligibility="eligible",
	)
	candidate = CandidateRecord(
		id="candidate-1",
		organization_id="org-1",
		full_name="Ada Lovelace",
		email="ada@example.com",
		location="London",
	)
	quality = resume_quality_payload(
		ResumeVersion(
			id="version-1",
			resume_document_id="document-1",
			version=1,
			quality_state="ready",
		)
	)

	values = export_row_values(evaluation, candidate, quality)

	assert set(values) == set(EXPORT_COLUMNS)
	assert values["candidate_name"] == "Ada Lovelace"
	assert values["score"] == "82"
	assert values["quality_state"] == "ready"


def test_resolve_export_columns_defaults_to_the_full_ordered_set() -> None:
	assert resolve_export_columns(None, None) == list(EXPORT_COLUMNS.items())


def test_resolve_export_columns_orders_and_renames() -> None:
	resolved = resolve_export_columns(
		["score", "candidate_name"], ["Fit", "Candidate"]
	)

	assert resolved == [("score", "Fit"), ("candidate_name", "Candidate")]


def test_resolve_export_columns_rejects_unknown_columns() -> None:
	with pytest.raises(APIError, match="Unknown export column"):
		resolve_export_columns(["score", "hacker"], None)


def test_resolve_export_columns_rejects_mismatched_labels() -> None:
	with pytest.raises(APIError, match="labels"):
		resolve_export_columns(["score", "candidate_name"], ["Fit"])
