from datetime import UTC, datetime

from app.api.routes import (
	independent_evaluation_storage_keys,
	independent_evaluation_summary,
)
from app.persistence.models import IndependentEvaluation


def evaluation(**overrides: object) -> IndependentEvaluation:
	values: dict[str, object] = {
		"id": "evaluation-1",
		"user_id": "candidate-1",
		"storage_key": "resumes/source.txt",
		"original_name": "resume.txt",
		"media_type": "text/plain",
		"status": "complete",
		"created_at": datetime(2026, 8, 25, tzinfo=UTC),
	}
	values.update(overrides)
	return IndependentEvaluation(**values)


def test_uploaded_job_description_is_reported_in_candidate_history() -> None:
	item = evaluation(job_description_key="jobs/role.txt")

	assert independent_evaluation_summary(item)["jobDescriptionProvided"] is True


def test_candidate_deletion_includes_every_owned_artifact() -> None:
	item = evaluation(
		job_description_key="jobs/role.txt",
		improved_resume_key="resumes/corrected.docx",
	)

	assert independent_evaluation_storage_keys(item) == [
		"resumes/source.txt",
		"jobs/role.txt",
		"resumes/corrected.docx",
	]
