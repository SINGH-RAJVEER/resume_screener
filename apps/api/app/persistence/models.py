from datetime import datetime

from sqlalchemy import (
	Boolean,
	CheckConstraint,
	DateTime,
	Float,
	ForeignKey,
	ForeignKeyConstraint,
	Integer,
	Text,
	UniqueConstraint,
	func,
	text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
	__tablename__ = "user"
	__table_args__ = (UniqueConstraint("email", name="uq_user_email"),)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	name: Mapped[str] = mapped_column(Text, nullable=False)
	email: Mapped[str] = mapped_column(Text, nullable=False)
	email_verified: Mapped[bool] = mapped_column(
		Boolean, nullable=False, default=False, server_default="false"
	)
	image: Mapped[str | None] = mapped_column(Text, nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class Account(Base):
	__tablename__ = "account"
	__table_args__ = (
		UniqueConstraint("provider_id", "account_id", name="uq_account_provider_account"),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	account_id: Mapped[str] = mapped_column(Text, nullable=False)
	provider_id: Mapped[str] = mapped_column(Text, nullable=False)
	user_id: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
	password: Mapped[str | None] = mapped_column(Text, nullable=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class Organization(Base):
	__tablename__ = "organization"

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	name: Mapped[str] = mapped_column(Text, nullable=False)
	retention_days: Mapped[int] = mapped_column(
		Integer, nullable=False, server_default=text("90")
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class OrganizationMember(Base):
	__tablename__ = "organization_member"
	__table_args__ = (
		CheckConstraint("role IN ('owner', 'recruiter', 'viewer')", name="ck_member_role"),
		UniqueConstraint("organization_id", "user_id", name="uq_organization_member"),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	organization_id: Mapped[str] = mapped_column(
		ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
	)
	user_id: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
	role: Mapped[str] = mapped_column(Text, nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class CandidateRecord(Base):
	__tablename__ = "candidate_record"
	__table_args__ = (
		UniqueConstraint("organization_id", "id", name="uq_candidate_record_organization"),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	organization_id: Mapped[str] = mapped_column(
		ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
	)
	user_id: Mapped[str | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"))
	full_name: Mapped[str | None] = mapped_column(Text)
	email: Mapped[str | None] = mapped_column(Text)
	phone: Mapped[str | None] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class ResumeDocument(Base):
	__tablename__ = "resume_document"
	__table_args__ = (
		CheckConstraint(
			"(owner_user_id IS NOT NULL) <> (organization_id IS NOT NULL)",
			name="ck_resume_document_owner",
		),
		UniqueConstraint("organization_id", "id", name="uq_resume_document_organization"),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
	organization_id: Mapped[str | None] = mapped_column(
		ForeignKey("organization.id", ondelete="CASCADE")
	)
	candidate_record_id: Mapped[str | None] = mapped_column(
		ForeignKey("candidate_record.id", ondelete="SET NULL")
	)
	storage_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
	checksum: Mapped[str] = mapped_column(Text, nullable=False)
	media_type: Mapped[str] = mapped_column(Text, nullable=False)
	size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
	original_name: Mapped[str] = mapped_column(Text, nullable=False)
	retention_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class ResumeVersion(Base):
	__tablename__ = "resume_version"
	__table_args__ = (
		ForeignKeyConstraint(
			["organization_id", "resume_document_id"],
			["resume_document.organization_id", "resume_document.id"],
			ondelete="CASCADE",
		),
		UniqueConstraint("resume_document_id", "version", name="uq_resume_version"),
		UniqueConstraint("organization_id", "id", name="uq_resume_version_organization"),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	organization_id: Mapped[str | None] = mapped_column(Text)
	resume_document_id: Mapped[str] = mapped_column(Text, nullable=False)
	version: Mapped[int] = mapped_column(Integer, nullable=False)
	extraction_blocks: Mapped[dict[str, object] | None] = mapped_column(JSONB)
	structured_facts: Mapped[dict[str, object] | None] = mapped_column(JSONB)
	normalized_facts: Mapped[dict[str, object] | None] = mapped_column(JSONB)
	quality_state: Mapped[str] = mapped_column(
		Text, nullable=False, server_default=text("'pending'")
	)
	parser_version: Mapped[str | None] = mapped_column(Text)
	schema_version: Mapped[str | None] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class Job(Base):
	__tablename__ = "job"
	__table_args__ = (UniqueConstraint("organization_id", "id", name="uq_job_organization"),)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	organization_id: Mapped[str] = mapped_column(
		ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
	)
	title: Mapped[str] = mapped_column(Text, nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class JobVersion(Base):
	__tablename__ = "job_version"
	__table_args__ = (UniqueConstraint("job_id", "version", name="uq_job_version"),)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	job_id: Mapped[str] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
	version: Mapped[int] = mapped_column(Integer, nullable=False)
	source_text: Mapped[str] = mapped_column(Text, nullable=False)
	normalized_text: Mapped[str | None] = mapped_column(Text)
	source_media_type: Mapped[str] = mapped_column(Text, nullable=False)
	draft_requirements: Mapped[dict[str, object] | None] = mapped_column(JSONB)
	schema_version: Mapped[str | None] = mapped_column(Text)
	confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class JobRequirement(Base):
	__tablename__ = "job_requirement"
	__table_args__ = (
		CheckConstraint(
			"kind IN ('required', 'preferred', 'ignored', 'hard_gate')", name="ck_requirement_kind"
		),
		CheckConstraint("weight > 0", name="ck_requirement_weight"),
		UniqueConstraint("job_version_id", "stable_id", name="uq_job_requirement_stable_id"),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	job_version_id: Mapped[str] = mapped_column(
		ForeignKey("job_version.id", ondelete="CASCADE"), nullable=False
	)
	stable_id: Mapped[str] = mapped_column(Text, nullable=False)
	kind: Mapped[str] = mapped_column(Text, nullable=False)
	weight: Mapped[int] = mapped_column(Integer, nullable=False)
	normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
	aliases: Mapped[list[str]] = mapped_column(
		JSONB, nullable=False, server_default=text("'[]'::jsonb")
	)
	source_evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
	confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResumeSubmission(Base):
	__tablename__ = "resume_submission"
	__table_args__ = (
		ForeignKeyConstraint(
			["organization_id", "job_id"],
			["job.organization_id", "job.id"],
			ondelete="CASCADE",
		),
		ForeignKeyConstraint(
			["organization_id", "candidate_record_id"],
			["candidate_record.organization_id", "candidate_record.id"],
			ondelete="CASCADE",
		),
		ForeignKeyConstraint(
			["organization_id", "resume_version_id"],
			["resume_version.organization_id", "resume_version.id"],
			ondelete="RESTRICT",
		),
		UniqueConstraint(
			"job_id", "candidate_record_id", "resume_version_id", name="uq_submission"
		),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	organization_id: Mapped[str] = mapped_column(
		ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
	)
	job_id: Mapped[str] = mapped_column(Text, nullable=False)
	candidate_record_id: Mapped[str] = mapped_column(Text, nullable=False)
	resume_version_id: Mapped[str] = mapped_column(Text, nullable=False)
	submitting_user_id: Mapped[str | None] = mapped_column(
		ForeignKey("user.id", ondelete="SET NULL")
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class ProcessingJob(Base):
	__tablename__ = "processing_job"
	__table_args__ = (
		CheckConstraint("attempt_count >= 0", name="ck_processing_job_attempt_count"),
		CheckConstraint("maximum_attempts > 0", name="ck_processing_job_maximum_attempts"),
		UniqueConstraint("type", "idempotency_key", name="uq_processing_job_idempotency"),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	type: Mapped[str] = mapped_column(Text, nullable=False)
	status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ready'"))
	payload_reference: Mapped[str] = mapped_column(Text, nullable=False)
	idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
	attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
	maximum_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
	available_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
	lease_token: Mapped[str | None] = mapped_column(Text)
	lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	safe_error: Mapped[str | None] = mapped_column(Text)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class Evaluation(Base):
	__tablename__ = "evaluation"
	__table_args__ = (
		CheckConstraint(
			"eligibility IN ('pending', 'eligible', 'needs_review', 'not_eligible')",
			name="ck_evaluation_eligibility",
		),
		UniqueConstraint(
			"resume_submission_id", "job_version_id", name="uq_evaluation_submission_job_version"
		),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	resume_submission_id: Mapped[str] = mapped_column(
		ForeignKey("resume_submission.id", ondelete="CASCADE"), nullable=False
	)
	job_version_id: Mapped[str] = mapped_column(
		ForeignKey("job_version.id", ondelete="RESTRICT"), nullable=False
	)
	resume_version_id: Mapped[str] = mapped_column(
		ForeignKey("resume_version.id", ondelete="RESTRICT"), nullable=False
	)
	status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
	score: Mapped[int | None] = mapped_column(Integer)
	evidence_coverage: Mapped[int | None] = mapped_column(Integer)
	eligibility: Mapped[str] = mapped_column(
		Text, nullable=False, server_default=text("'pending'")
	)
	quality_state: Mapped[str] = mapped_column(
		Text, nullable=False, server_default=text("'pending'")
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
	completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RequirementAssessment(Base):
	__tablename__ = "requirement_assessment"
	__table_args__ = (
		CheckConstraint(
			"outcome IN ('met', 'partial', 'not_met', 'unknown')", name="ck_assessment_outcome"
		),
		UniqueConstraint(
			"evaluation_id", "job_requirement_id", name="uq_assessment_evaluation_requirement"
		),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	evaluation_id: Mapped[str] = mapped_column(
		ForeignKey("evaluation.id", ondelete="CASCADE"), nullable=False
	)
	job_requirement_id: Mapped[str] = mapped_column(
		ForeignKey("job_requirement.id", ondelete="RESTRICT"), nullable=False
	)
	outcome: Mapped[str] = mapped_column(Text, nullable=False)
	confidence: Mapped[float] = mapped_column(Float, nullable=False)
	reasoning: Mapped[str] = mapped_column(Text, nullable=False)
	evidence: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
	deterministic_evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB)
	semantic_evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class Invitation(Base):
	__tablename__ = "invitation"
	__table_args__ = (UniqueConstraint("token_hash", name="uq_invitation_token_hash"),)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	job_id: Mapped[str] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
	creator_user_id: Mapped[str] = mapped_column(
		ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
	)
	token_hash: Mapped[str] = mapped_column(Text, nullable=False)
	expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
	redeeming_user_id: Mapped[str | None] = mapped_column(
		ForeignKey("user.id", ondelete="SET NULL")
	)
	resume_submission_id: Mapped[str | None] = mapped_column(
		ForeignKey("resume_submission.id", ondelete="SET NULL")
	)
	revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)
