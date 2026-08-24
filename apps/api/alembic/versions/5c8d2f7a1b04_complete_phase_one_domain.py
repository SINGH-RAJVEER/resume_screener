"""complete phase one domain

Revision ID: 5c8d2f7a1b04
Revises: b7e2c41d9f60
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "5c8d2f7a1b04"
down_revision: str | None = "b7e2c41d9f60"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
	op.add_column("resume_version", sa.Column("parser_configuration_version", sa.Text()))
	op.add_column("resume_version", sa.Column("extraction_prompt_version", sa.Text()))
	op.add_column(
		"job_version",
		sa.Column("prompt_version", sa.Text(), nullable=False, server_default="1"),
	)
	op.add_column(
		"job_version",
		sa.Column("compiler_version", sa.Text(), nullable=False, server_default="compiler-2"),
	)
	op.create_unique_constraint("uq_job_version_job", "job_version", ["job_id", "id"])
	op.create_table(
		"batch_evaluation",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column("organization_id", sa.Text(), nullable=False),
		sa.Column("job_id", sa.Text(), nullable=False),
		sa.Column("job_version_id", sa.Text(), nullable=False),
		sa.Column(
			"created_by_user_id",
			sa.Text(),
			sa.ForeignKey("user.id", ondelete="RESTRICT"),
			nullable=False,
		),
		sa.Column("requirement_schema_version", sa.Text(), nullable=False),
		sa.Column(
			"scoring_policy_version",
			sa.Text(),
			nullable=False,
			server_default="criterion-weighted-1",
		),
		sa.Column(
			"model_configuration",
			JSONB(),
			nullable=False,
			server_default=sa.text("'{}'::jsonb"),
		),
		sa.Column(
			"created_at",
			sa.DateTime(timezone=True),
			nullable=False,
			server_default=sa.func.now(),
		),
		sa.ForeignKeyConstraint(
			["organization_id", "job_id"],
			["job.organization_id", "job.id"],
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["job_id", "job_version_id"],
			["job_version.job_id", "job_version.id"],
			ondelete="RESTRICT",
		),
	)
	op.drop_constraint(
		"uq_evaluation_submission_job_version", "evaluation", type_="unique"
	)
	op.add_column(
		"evaluation",
		sa.Column(
			"batch_evaluation_id",
			sa.Text(),
			sa.ForeignKey("batch_evaluation.id", ondelete="CASCADE"),
		),
	)
	op.add_column(
		"evaluation",
		sa.Column(
			"scoring_policy_version",
			sa.Text(),
			nullable=False,
			server_default="criterion-weighted-1",
		),
	)
	op.add_column(
		"evaluation",
		sa.Column(
			"assessment_schema_version", sa.Text(), nullable=False, server_default="1"
		),
	)
	op.add_column(
		"evaluation",
		sa.Column(
			"assessment_prompt_version", sa.Text(), nullable=False, server_default="1"
		),
	)
	op.add_column("evaluation", sa.Column("rank", sa.Integer()))
	op.create_check_constraint(
		"ck_evaluation_status",
		"evaluation",
		"status IN ('pending', 'processing', 'complete', 'failed')",
	)
	op.create_check_constraint(
		"ck_evaluation_score", "evaluation", "score IS NULL OR score BETWEEN 0 AND 100"
	)
	op.create_check_constraint(
		"ck_evaluation_evidence_coverage",
		"evaluation",
		"evidence_coverage IS NULL OR evidence_coverage BETWEEN 0 AND 100",
	)
	op.create_unique_constraint(
		"uq_evaluation_batch_submission",
		"evaluation",
		["batch_evaluation_id", "resume_submission_id"],
	)
	op.create_table(
		"batch_evaluation_submission",
		sa.Column(
			"batch_evaluation_id",
			sa.Text(),
			sa.ForeignKey("batch_evaluation.id", ondelete="CASCADE"),
			primary_key=True,
		),
		sa.Column(
			"resume_submission_id",
			sa.Text(),
			sa.ForeignKey("resume_submission.id", ondelete="RESTRICT"),
			primary_key=True,
		),
		sa.Column(
			"created_at",
			sa.DateTime(timezone=True),
			nullable=False,
			server_default=sa.func.now(),
		),
	)
	op.create_table(
		"review_decision",
		sa.Column("id", sa.Text(), primary_key=True),
		sa.Column(
			"evaluation_id",
			sa.Text(),
			sa.ForeignKey("evaluation.id", ondelete="CASCADE"),
			nullable=False,
		),
		sa.Column(
			"reviewer_user_id",
			sa.Text(),
			sa.ForeignKey("user.id", ondelete="RESTRICT"),
			nullable=False,
		),
		sa.Column("eligibility", sa.Text(), nullable=False),
		sa.Column("reason", sa.Text(), nullable=False),
		sa.Column(
			"created_at",
			sa.DateTime(timezone=True),
			nullable=False,
			server_default=sa.func.now(),
		),
		sa.CheckConstraint(
			"eligibility IN ('eligible', 'needs_review', 'not_eligible')",
			name="ck_review_decision_eligibility",
		),
	)
	op.add_column("independent_evaluation", sa.Column("parser_version", sa.Text()))
	op.add_column(
		"independent_evaluation",
		sa.Column(
			"parser_configuration_version",
			sa.Text(),
			nullable=False,
			server_default="resume-parser-1",
		),
	)
	op.add_column("independent_evaluation", sa.Column("schema_version", sa.Text()))
	op.add_column(
		"independent_evaluation",
		sa.Column(
			"extraction_prompt_version", sa.Text(), nullable=False, server_default="1"
		),
	)
	op.add_column(
		"independent_evaluation",
		sa.Column(
			"scoring_policy_version",
			sa.Text(),
			nullable=False,
			server_default="criterion-weighted-1",
		),
	)


def downgrade() -> None:
	for column in (
		"scoring_policy_version",
		"extraction_prompt_version",
		"schema_version",
		"parser_configuration_version",
		"parser_version",
	):
		op.drop_column("independent_evaluation", column)
	op.drop_table("review_decision")
	op.drop_table("batch_evaluation_submission")
	op.drop_constraint("uq_evaluation_batch_submission", "evaluation", type_="unique")
	op.drop_constraint("ck_evaluation_evidence_coverage", "evaluation", type_="check")
	op.drop_constraint("ck_evaluation_score", "evaluation", type_="check")
	op.drop_constraint("ck_evaluation_status", "evaluation", type_="check")
	for column in (
		"rank",
		"assessment_prompt_version",
		"assessment_schema_version",
		"scoring_policy_version",
		"batch_evaluation_id",
	):
		op.drop_column("evaluation", column)
	op.create_unique_constraint(
		"uq_evaluation_submission_job_version",
		"evaluation",
		["resume_submission_id", "job_version_id"],
	)
	op.drop_table("batch_evaluation")
	op.drop_constraint("uq_job_version_job", "job_version", type_="unique")
	op.drop_column("job_version", "compiler_version")
	op.drop_column("job_version", "prompt_version")
	op.drop_column("resume_version", "extraction_prompt_version")
	op.drop_column("resume_version", "parser_configuration_version")
