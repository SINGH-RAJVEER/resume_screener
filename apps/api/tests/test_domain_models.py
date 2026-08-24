from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Table, UniqueConstraint

from app.persistence.models import Base


def test_core_domain_tables_are_registered() -> None:
	assert {
		"organization",
		"organization_member",
		"candidate_record",
		"resume_document",
		"resume_version",
		"job",
		"job_version",
		"job_requirement",
		"resume_submission",
		"processing_job",
		"batch_evaluation",
		"batch_evaluation_submission",
		"evaluation",
		"requirement_assessment",
		"review_decision",
		"invitation",
	} <= set(Base.metadata.tables)


def test_core_domain_invariants_are_database_constraints() -> None:
	resume_document = Base.metadata.tables["resume_document"]
	processing_job = Base.metadata.tables["processing_job"]
	submission = Base.metadata.tables["resume_submission"]
	point_account = Base.metadata.tables["point_account"]
	point_ledger_entry = Base.metadata.tables["point_ledger_entry"]
	point_reservation = Base.metadata.tables["point_reservation"]
	job_version = Base.metadata.tables["job_version"]
	batch_evaluation = Base.metadata.tables["batch_evaluation"]
	evaluation = Base.metadata.tables["evaluation"]
	review_decision = Base.metadata.tables["review_decision"]

	assert constraint_names(resume_document, CheckConstraint) >= {"ck_resume_document_owner"}
	assert constraint_names(processing_job, CheckConstraint) >= {
		"ck_processing_job_attempt_count",
		"ck_processing_job_maximum_attempts",
	}
	assert constraint_names(processing_job, UniqueConstraint) >= {"uq_processing_job_idempotency"}
	assert foreign_key_targets(submission) >= {
		("organization_id", "job.organization_id"),
		("organization_id", "candidate_record.organization_id"),
		("organization_id", "resume_version.organization_id"),
	}
	assert constraint_names(point_account, CheckConstraint) >= {"ck_point_account_owner"}
	assert constraint_names(point_account, UniqueConstraint) >= {
		"uq_point_account_user",
		"uq_point_account_organization",
	}
	assert constraint_names(point_ledger_entry, CheckConstraint) >= {
		"ck_point_ledger_entry_nonzero_amount"
	}
	assert constraint_names(point_ledger_entry, UniqueConstraint) >= {
		"uq_point_ledger_entry_idempotency"
	}
	assert constraint_names(point_reservation, CheckConstraint) >= {
		"ck_point_reservation_positive_amount",
		"ck_point_reservation_state",
	}
	assert constraint_names(job_version, UniqueConstraint) >= {"uq_job_version_job"}
	assert foreign_key_targets(batch_evaluation) >= {
		("organization_id", "job.organization_id"),
		("job_id", "job_version.job_id"),
	}
	assert constraint_names(evaluation, CheckConstraint) >= {
		"ck_evaluation_status",
		"ck_evaluation_score",
		"ck_evaluation_evidence_coverage",
	}
	assert constraint_names(evaluation, UniqueConstraint) >= {
		"uq_evaluation_batch_submission"
	}
	assert constraint_names(review_decision, CheckConstraint) >= {
		"ck_review_decision_eligibility"
	}


def test_persisted_artifacts_include_policy_versions() -> None:
	resume_version = Base.metadata.tables["resume_version"]
	job_version = Base.metadata.tables["job_version"]
	evaluation = Base.metadata.tables["evaluation"]
	independent_evaluation = Base.metadata.tables["independent_evaluation"]

	assert {
		"parser_version",
		"parser_configuration_version",
		"schema_version",
		"extraction_prompt_version",
	} <= set(resume_version.columns)
	assert {"schema_version", "prompt_version", "compiler_version"} <= set(
		job_version.columns
	)
	assert {
		"scoring_policy_version",
		"assessment_schema_version",
		"assessment_prompt_version",
	} <= set(evaluation.columns)
	assert {
		"parser_version",
		"parser_configuration_version",
		"schema_version",
		"extraction_prompt_version",
		"scoring_policy_version",
	} <= set(independent_evaluation.columns)


def constraint_names(
	table: Table, constraint_type: type[CheckConstraint | UniqueConstraint]
) -> set[str]:
	constraints = table.constraints
	return {
		str(constraint.name)
		for constraint in constraints
		if isinstance(constraint, constraint_type) and constraint.name is not None
	}


def foreign_key_targets(table: Table) -> set[tuple[str, str]]:
	return {
		(constraint.column_keys[0], element.target_fullname)
		for constraint in table.constraints
		if isinstance(constraint, ForeignKeyConstraint)
		for element in constraint.elements
	}
