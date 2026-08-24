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
		"evaluation",
		"requirement_assessment",
		"invitation",
	} <= set(Base.metadata.tables)


def test_core_domain_invariants_are_database_constraints() -> None:
	resume_document = Base.metadata.tables["resume_document"]
	processing_job = Base.metadata.tables["processing_job"]
	submission = Base.metadata.tables["resume_submission"]
	point_account = Base.metadata.tables["point_account"]
	point_ledger_entry = Base.metadata.tables["point_ledger_entry"]
	point_reservation = Base.metadata.tables["point_reservation"]

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
