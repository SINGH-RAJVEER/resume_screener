from datetime import datetime

from sqlalchemy import (
    JSON,
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

from ..domain.versions import (
    JOB_REQUIREMENTS_COMPILER_VERSION,
    JOB_REQUIREMENTS_PROMPT_VERSION,
    PARSER_CONFIGURATION_VERSION,
    SCORING_POLICY_VERSION,
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint("account_type IN ('employer', 'candidate')", name="ck_user_account_type"),
        UniqueConstraint("email", name="uq_user_email"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'candidate'")
    )
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
    __table_args__ = (
        CheckConstraint(
            "default_member_role IN ('recruiter', 'viewer')",
            name="ck_organization_default_member_role",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_member_role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'viewer'")
    )
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("90"))
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
        # An employer user belongs to at most one organization.
        UniqueConstraint("user_id", name="uq_organization_member_user"),
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


class OrganizationEmailDomain(Base):
    __tablename__ = "organization_email_domain"
    __table_args__ = (UniqueConstraint("domain", name="uq_organization_email_domain"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OrganizationAllowedEmail(Base):
    __tablename__ = "organization_allowed_email"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_organization_allowed_email"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
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
    location: Mapped[str | None] = mapped_column(Text)
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
		CheckConstraint(
			"quality_state IN ('pending', 'ready', 'review_required', 'failed')",
			name="ck_resume_version_quality_state",
		),
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
    parser_configuration_version: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[str | None] = mapped_column(Text)
    extraction_prompt_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResumeBlockEmbedding(Base):
    __tablename__ = "resume_block_embedding"

    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_version.id", ondelete="CASCADE"), primary_key=True
    )
    block_id: Mapped[str] = mapped_column(Text, primary_key=True)
    model: Mapped[str] = mapped_column(Text, primary_key=True)
    text_hash: Mapped[str] = mapped_column(Text, nullable=False)
    vector: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"

    model: Mapped[str] = mapped_column(Text, primary_key=True)
    text_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    vector: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
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
    application_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class JobVersion(Base):
    __tablename__ = "job_version"
    __table_args__ = (
		UniqueConstraint("job_id", "version", name="uq_job_version"),
		UniqueConstraint("job_id", "id", name="uq_job_version_job"),
	)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    source_media_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_storage_key: Mapped[str | None] = mapped_column(Text)
    draft_requirements: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    schema_version: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(
		Text, nullable=False, server_default=text(f"'{JOB_REQUIREMENTS_PROMPT_VERSION}'")
	)
    compiler_version: Mapped[str] = mapped_column(
		Text, nullable=False, server_default=text(f"'{JOB_REQUIREMENTS_COMPILER_VERSION}'")
	)
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
        CheckConstraint(
            "assessability IN ('resume_evidence', 'candidate_attestation', "
            "'recruiter_review', 'prohibited', 'unclear')",
            name="ck_requirement_assessability",
        ),
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
    category: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'other'"))
    source_modality: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'unclear'")
    )
    assessability: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'unclear'")
    )
    predicate: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
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
		UniqueConstraint(
			"organization_id", "job_id", "id", name="uq_submission_organization_job"
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


class BatchEvaluation(Base):
	__tablename__ = "batch_evaluation"
	__table_args__ = (
		ForeignKeyConstraint(
			["organization_id", "job_id"],
			["job.organization_id", "job.id"],
			ondelete="CASCADE",
		),
		ForeignKeyConstraint(
			["job_id", "job_version_id"],
			["job_version.job_id", "job_version.id"],
			ondelete="RESTRICT",
		),
		UniqueConstraint(
			"organization_id", "job_id", "id", name="uq_batch_evaluation_organization_job"
		),
		UniqueConstraint("organization_id", "id", name="uq_batch_evaluation_organization"),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	organization_id: Mapped[str] = mapped_column(Text, nullable=False)
	job_id: Mapped[str] = mapped_column(Text, nullable=False)
	job_version_id: Mapped[str] = mapped_column(Text, nullable=False)
	created_by_user_id: Mapped[str] = mapped_column(
		ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
	)
	requirement_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
	scoring_policy_version: Mapped[str] = mapped_column(
		Text, nullable=False, server_default=text(f"'{SCORING_POLICY_VERSION}'")
	)
	model_configuration: Mapped[dict[str, object]] = mapped_column(
		JSONB, nullable=False, server_default=text("'{}'::jsonb")
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class Evaluation(Base):
    __tablename__ = "evaluation"
    __table_args__ = (
		CheckConstraint(
			"status IN ('pending', 'processing', 'complete', 'failed')",
			name="ck_evaluation_status",
		),
        CheckConstraint(
            "eligibility IN ('pending', 'eligible', 'needs_review', 'not_eligible')",
            name="ck_evaluation_eligibility",
        ),
		CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_evaluation_score"),
		CheckConstraint(
			"evidence_coverage IS NULL OR evidence_coverage BETWEEN 0 AND 100",
			name="ck_evaluation_evidence_coverage",
		),
		CheckConstraint(
			"quality_state IN ('pending', 'ready', 'review_required', 'failed')",
			name="ck_evaluation_quality_state",
		),
        UniqueConstraint(
			"batch_evaluation_id",
			"resume_submission_id",
			name="uq_evaluation_batch_submission",
        ),
		UniqueConstraint("batch_evaluation_id", "id", name="uq_evaluation_batch"),
		ForeignKeyConstraint(
			["batch_evaluation_id", "resume_submission_id"],
			[
				"batch_evaluation_submission.batch_evaluation_id",
				"batch_evaluation_submission.resume_submission_id",
			],
			ondelete="CASCADE",
		),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    batch_evaluation_id: Mapped[str | None] = mapped_column(
        ForeignKey("batch_evaluation.id", ondelete="CASCADE")
    )
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
    eligibility: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    quality_state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    scoring_policy_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(f"'{SCORING_POLICY_VERSION}'")
    )
    assessment_schema_version: Mapped[str | None] = mapped_column(Text)
    assessment_prompt_version: Mapped[str | None] = mapped_column(Text)
    # Safe reason recorded when the model assessment stage degraded to
    # deterministic outcomes, so the degradation outlives the worker run.
    assessment_degradation: Mapped[str | None] = mapped_column(Text)
    rank: Mapped[int | None] = mapped_column(Integer)
    point_reservation_id: Mapped[str | None] = mapped_column(
        ForeignKey("point_reservation.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BatchEvaluationSubmission(Base):
	__tablename__ = "batch_evaluation_submission"
	__table_args__ = (
		ForeignKeyConstraint(
			["organization_id", "job_id", "batch_evaluation_id"],
			[
				"batch_evaluation.organization_id",
				"batch_evaluation.job_id",
				"batch_evaluation.id",
			],
			ondelete="CASCADE",
		),
		ForeignKeyConstraint(
			["organization_id", "job_id", "resume_submission_id"],
			[
				"resume_submission.organization_id",
				"resume_submission.job_id",
				"resume_submission.id",
			],
			ondelete="RESTRICT",
		),
	)

	organization_id: Mapped[str] = mapped_column(Text, nullable=False)
	job_id: Mapped[str] = mapped_column(Text, nullable=False)
	batch_evaluation_id: Mapped[str] = mapped_column(Text, primary_key=True)
	resume_submission_id: Mapped[str] = mapped_column(Text, primary_key=True)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


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
    lexical_evidence: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReviewDecision(Base):
	__tablename__ = "review_decision"
	__table_args__ = (
		CheckConstraint(
			"eligibility IN ('eligible', 'needs_review', 'not_eligible')",
			name="ck_review_decision_eligibility",
		),
		ForeignKeyConstraint(
			["organization_id", "batch_evaluation_id"],
			["batch_evaluation.organization_id", "batch_evaluation.id"],
			ondelete="CASCADE",
		),
		ForeignKeyConstraint(
			["batch_evaluation_id", "evaluation_id"],
			["evaluation.batch_evaluation_id", "evaluation.id"],
			ondelete="CASCADE",
		),
	)

	id: Mapped[str] = mapped_column(Text, primary_key=True)
	organization_id: Mapped[str] = mapped_column(Text, nullable=False)
	batch_evaluation_id: Mapped[str] = mapped_column(Text, nullable=False)
	evaluation_id: Mapped[str] = mapped_column(Text, nullable=False)
	reviewer_user_id: Mapped[str] = mapped_column(
		ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
	)
	eligibility: Mapped[str] = mapped_column(Text, nullable=False)
	reason: Mapped[str] = mapped_column(Text, nullable=False)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), nullable=False, server_default=func.now()
	)


class Invitation(Base):
    __tablename__ = "invitation"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_invitation_token_hash"),
        UniqueConstraint("passcode_hash", name="uq_invitation_passcode_hash"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"), nullable=False)
    creator_user_id: Mapped[str] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    passcode_hash: Mapped[str | None] = mapped_column(Text)
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


class IndependentEvaluation(Base):
    __tablename__ = "independent_evaluation"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'complete', 'failed')",
            name="ck_independent_evaluation_status",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    job_description: Mapped[str | None] = mapped_column(Text)
    job_description_key: Mapped[str | None] = mapped_column(Text)
    job_description_media_type: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    score: Mapped[int | None] = mapped_column(Integer)
    suggestions: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    improved_resume_key: Mapped[str | None] = mapped_column(Text)
    improved_resume_unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    normalized_facts: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    parser_version: Mapped[str | None] = mapped_column(Text)
    parser_configuration_version: Mapped[str] = mapped_column(
		Text, nullable=False, server_default=text(f"'{PARSER_CONFIGURATION_VERSION}'")
	)
    schema_version: Mapped[str | None] = mapped_column(Text)
    extraction_prompt_version: Mapped[str | None] = mapped_column(Text)
    scoring_policy_version: Mapped[str] = mapped_column(
		Text, nullable=False, server_default=text(f"'{SCORING_POLICY_VERSION}'")
	)
    safe_error: Mapped[str | None] = mapped_column(Text)
    point_reservation_id: Mapped[str | None] = mapped_column(
        ForeignKey("point_reservation.id", ondelete="SET NULL")
    )
    free_week_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PointAccount(Base):
    __tablename__ = "point_account"
    __table_args__ = (
        CheckConstraint(
            "(owner_user_id IS NOT NULL) <> (organization_id IS NOT NULL)",
            name="ck_point_account_owner",
        ),
        UniqueConstraint("owner_user_id", name="uq_point_account_user"),
        UniqueConstraint("organization_id", name="uq_point_account_organization"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PointLedgerEntry(Base):
    __tablename__ = "point_ledger_entry"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_point_ledger_entry_nonzero_amount"),
        UniqueConstraint("account_id", "idempotency_key", name="uq_point_ledger_entry_idempotency"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("point_account.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PointReservation(Base):
    __tablename__ = "point_reservation"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_point_reservation_positive_amount"),
        CheckConstraint(
            "state IN ('reserved', 'settled', 'released')", name="ck_point_reservation_state"
        ),
        UniqueConstraint("account_id", "idempotency_key", name="uq_point_reservation_idempotency"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("point_account.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'reserved'"))
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OrganizationEntitlement(Base):
    """Manually provisioned enterprise access that bypasses point purchases."""

    __tablename__ = "organization_entitlement"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    provisioned_by: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WeeklyFreeUse(Base):
    __tablename__ = "weekly_free_use"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_weekly_free_use"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RazorpayOrder(Base):
    __tablename__ = "razorpay_order"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'paid', 'refunded', 'failed')",
            name="ck_razorpay_order_status",
        ),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    razorpay_order_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("point_account.id", ondelete="RESTRICT"), nullable=False
    )
    purchaser_user_id: Mapped[str] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    pack_id: Mapped[str] = mapped_column(Text, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'INR'"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'created'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RazorpayPayment(Base):
    __tablename__ = "razorpay_payment"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    razorpay_payment_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    order_row_id: Mapped[str] = mapped_column(
        ForeignKey("razorpay_order.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str | None] = mapped_column(Text)
    amount_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    refunded_inr: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    points_granted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    signature_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RazorpayWebhookEvent(Base):
    """Durable idempotent inbox; events tolerate retries and out-of-order delivery."""

    __tablename__ = "razorpay_webhook_event"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Generic JSON keeps the webhook inbox portable; events are never queried
    # with PostgreSQL JSON operators.
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
