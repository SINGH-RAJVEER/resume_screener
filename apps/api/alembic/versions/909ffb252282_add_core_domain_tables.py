"""add core domain tables

Revision ID: 909ffb252282
Revises: 0001_initial
Create Date: 2026-08-21 04:48:31.009724
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "909ffb252282"
down_revision: str | None = "0001_initial"
branch_labels: Sequence[str] | None = None


def upgrade() -> None:
	op.create_table(
		"organization",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("name", sa.Text(), nullable=False),
		sa.Column("retention_days", sa.Integer(), nullable=False, server_default="90"),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
	)
	op.create_table(
		"organization_member",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("organization_id", sa.Text(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
		sa.Column("user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
		sa.Column("role", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.CheckConstraint("role IN ('owner', 'recruiter', 'viewer')", name="ck_member_role"),
		sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_member"),
	)
	op.create_table(
		"candidate_record",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("organization_id", sa.Text(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
		sa.Column("user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="SET NULL")),
		sa.Column("full_name", sa.Text()),
		sa.Column("email", sa.Text()),
		sa.Column("phone", sa.Text()),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.UniqueConstraint("organization_id", "id", name="uq_candidate_record_organization"),
	)
	op.create_table(
		"resume_document",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("owner_user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="CASCADE")),
		sa.Column("organization_id", sa.Text(), sa.ForeignKey("organization.id", ondelete="CASCADE")),
		sa.Column("candidate_record_id", sa.Text(), sa.ForeignKey("candidate_record.id", ondelete="SET NULL")),
		sa.Column("storage_key", sa.Text(), nullable=False, unique=True),
		sa.Column("checksum", sa.Text(), nullable=False),
		sa.Column("media_type", sa.Text(), nullable=False),
		sa.Column("size_bytes", sa.Integer(), nullable=False),
		sa.Column("original_name", sa.Text(), nullable=False),
		sa.Column("retention_date", sa.DateTime(timezone=True), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.CheckConstraint("(owner_user_id IS NOT NULL) <> (organization_id IS NOT NULL)", name="ck_resume_document_owner"),
		sa.UniqueConstraint("organization_id", "id", name="uq_resume_document_organization"),
	)
	op.create_table(
		"resume_version",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("organization_id", sa.Text()),
		sa.Column("resume_document_id", sa.Text(), nullable=False),
		sa.Column("version", sa.Integer(), nullable=False),
		sa.Column("extraction_blocks", postgresql.JSONB()),
		sa.Column("structured_facts", postgresql.JSONB()),
		sa.Column("normalized_facts", postgresql.JSONB()),
		sa.Column("quality_state", sa.Text(), nullable=False, server_default="pending"),
		sa.Column("parser_version", sa.Text()),
		sa.Column("schema_version", sa.Text()),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.ForeignKeyConstraint(["organization_id", "resume_document_id"], ["resume_document.organization_id", "resume_document.id"], ondelete="CASCADE"),
		sa.UniqueConstraint("resume_document_id", "version", name="uq_resume_version"),
		sa.UniqueConstraint("organization_id", "id", name="uq_resume_version_organization"),
	)
	op.create_table(
		"job",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("organization_id", sa.Text(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
		sa.Column("title", sa.Text(), nullable=False),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.UniqueConstraint("organization_id", "id", name="uq_job_organization"),
	)
	op.create_table(
		"job_version",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("job_id", sa.Text(), sa.ForeignKey("job.id", ondelete="CASCADE"), nullable=False),
		sa.Column("version", sa.Integer(), nullable=False),
		sa.Column("source_text", sa.Text(), nullable=False),
		sa.Column("normalized_text", sa.Text()),
		sa.Column("source_media_type", sa.Text(), nullable=False),
		sa.Column("draft_requirements", postgresql.JSONB()),
		sa.Column("schema_version", sa.Text()),
		sa.Column("confirmed_at", sa.DateTime(timezone=True)),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.UniqueConstraint("job_id", "version", name="uq_job_version"),
	)
	op.create_table(
		"job_requirement",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("job_version_id", sa.Text(), sa.ForeignKey("job_version.id", ondelete="CASCADE"), nullable=False),
		sa.Column("stable_id", sa.Text(), nullable=False),
		sa.Column("kind", sa.Text(), nullable=False),
		sa.Column("weight", sa.Integer(), nullable=False),
		sa.Column("normalized_text", sa.Text(), nullable=False),
		sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default="[]"),
		sa.Column("source_evidence", postgresql.JSONB(), nullable=False),
		sa.Column("confirmed_at", sa.DateTime(timezone=True)),
		sa.CheckConstraint("kind IN ('required', 'preferred', 'ignored', 'hard_gate')", name="ck_requirement_kind"),
		sa.CheckConstraint("weight > 0", name="ck_requirement_weight"),
		sa.UniqueConstraint("job_version_id", "stable_id", name="uq_job_requirement_stable_id"),
	)
	op.create_table(
		"resume_submission",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("organization_id", sa.Text(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
		sa.Column("job_id", sa.Text(), nullable=False),
		sa.Column("candidate_record_id", sa.Text(), nullable=False),
		sa.Column("resume_version_id", sa.Text(), nullable=False),
		sa.Column("submitting_user_id", sa.Text(), sa.ForeignKey("user.id", ondelete="SET NULL")),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.ForeignKeyConstraint(["organization_id", "job_id"], ["job.organization_id", "job.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["organization_id", "candidate_record_id"], ["candidate_record.organization_id", "candidate_record.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["organization_id", "resume_version_id"], ["resume_version.organization_id", "resume_version.id"], ondelete="RESTRICT"),
		sa.UniqueConstraint("job_id", "candidate_record_id", "resume_version_id", name="uq_submission"),
	)
	op.create_table(
		"processing_job",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("type", sa.Text(), nullable=False),
		sa.Column("status", sa.Text(), nullable=False, server_default="ready"),
		sa.Column("payload_reference", sa.Text(), nullable=False),
		sa.Column("idempotency_key", sa.Text(), nullable=False),
		sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
		sa.Column("maximum_attempts", sa.Integer(), nullable=False, server_default="3"),
		sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column("lease_token", sa.Text()),
		sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
		sa.Column("safe_error", sa.Text()),
		sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
		sa.CheckConstraint("attempt_count >= 0", name="ck_processing_job_attempt_count"),
		sa.CheckConstraint("maximum_attempts > 0", name="ck_processing_job_maximum_attempts"),
		sa.UniqueConstraint("type", "idempotency_key", name="uq_processing_job_idempotency"),
	)


def downgrade() -> None:
	for table in (
		"processing_job",
		"resume_submission",
		"job_requirement",
		"job_version",
		"job",
		"resume_version",
		"resume_document",
		"candidate_record",
		"organization_member",
		"organization",
	):
		op.drop_table(table)
