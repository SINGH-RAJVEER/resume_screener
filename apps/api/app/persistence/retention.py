"""Retention sweeping removes expired resume data across storage and tables.

Independent evaluations expire whole (source file, extracted facts, report,
improved DOCX). Employer documents expire with every submission, evaluation,
and embedding derived from them, so no candidate-identifying content survives
past the configured window.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..documents.storage import LocalObjectStorage
from .models import (
	BatchEvaluation,
	BatchEvaluationSubmission,
	Evaluation,
	IndependentEvaluation,
	ProcessingJob,
	ResumeDocument,
	ResumeSubmission,
	ResumeVersion,
)
from .points import release_in_session


@dataclass(frozen=True)
class RetentionResult:
	documents_purged: int
	independent_evaluations_purged: int


def independent_storage_keys(evaluation: IndependentEvaluation) -> list[str]:
	return [
		key
		for key in (
			evaluation.storage_key,
			evaluation.job_description_key,
			evaluation.improved_resume_key,
		)
		if key
	]


async def purge_expired_data(
	session: AsyncSession,
	storage: LocalObjectStorage,
	now: datetime,
) -> RetentionResult:
	documents = (
		await session.scalars(
			select(ResumeDocument)
			.where(ResumeDocument.retention_date <= now)
			.order_by(ResumeDocument.retention_date)
		)
	).all()
	evaluations = (
		await session.scalars(
			select(IndependentEvaluation)
			.where(IndependentEvaluation.retention_date <= now)
			.order_by(IndependentEvaluation.retention_date)
		)
	).all()

	document_keys = [document.storage_key for document in documents]
	evaluation_keys = [
		key
		for evaluation in evaluations
		for key in independent_storage_keys(evaluation)
	]

	await _purge_independent_evaluations(session, list(evaluations))
	await _purge_resume_documents(session, list(documents))

	# Objects go only after the deletes succeed; a crash between the two
	# leaves an unreachable object, never a dangling reference.
	for key in [*document_keys, *evaluation_keys]:
		storage.delete(key)

	return RetentionResult(
		documents_purged=len(documents),
		independent_evaluations_purged=len(evaluations),
	)


async def _purge_independent_evaluations(
	session: AsyncSession,
	evaluations: list[IndependentEvaluation],
) -> None:
	for evaluation in evaluations:
		if evaluation.point_reservation_id is not None:
			# An unsettled hold must return to the balance instead of
			# expiring with the report it paid for.
			await release_in_session(session, str(evaluation.point_reservation_id))
		await session.execute(
			delete(ProcessingJob).where(
				(ProcessingJob.type == "independent_evaluation_processing")
				& (ProcessingJob.payload_reference == evaluation.id)
			)
		)
		await session.delete(evaluation)


async def _purge_resume_documents(
	session: AsyncSession,
	documents: list[ResumeDocument],
) -> None:
	if not documents:
		return
	version_ids = select(ResumeVersion.id).where(
		ResumeVersion.resume_document_id.in_([document.id for document in documents])
	)
	submission_ids = select(ResumeSubmission.id).where(
		ResumeSubmission.resume_version_id.in_(version_ids)
	)
	# Evaluations first: their rows RESTRICT version deletion and their
	# children (assessments, review decisions) cascade from here.
	await session.execute(delete(Evaluation).where(Evaluation.resume_version_id.in_(version_ids)))
	await session.execute(
		delete(BatchEvaluationSubmission).where(
			BatchEvaluationSubmission.resume_submission_id.in_(submission_ids)
		)
	)
	await session.execute(delete(ResumeSubmission).where(ResumeSubmission.id.in_(submission_ids)))
	# Batches left without linked submissions or evaluations are empty shells.
	await session.execute(
		delete(BatchEvaluation).where(
			BatchEvaluation.id.not_in(select(BatchEvaluationSubmission.batch_evaluation_id))
			& BatchEvaluation.id.not_in(
				select(Evaluation.batch_evaluation_id).where(
					Evaluation.batch_evaluation_id.is_not(None)
				)
			)
		)
	)
	await session.execute(
		delete(ResumeDocument).where(ResumeDocument.id.in_([document.id for document in documents]))
	)
