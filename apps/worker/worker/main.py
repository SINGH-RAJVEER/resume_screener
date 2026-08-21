from __future__ import annotations

import asyncio
import json
import logging
import random
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import WorkerSettings, load_settings
from .documents.normalizer import normalize_resume
from .documents.parser import DocumentParseError, extract_blocks
from .evaluations.evaluator import evaluate

logger = logging.getLogger("resume-screener.worker")


class NonRetryableJobError(Exception):
	pass


@dataclass(frozen=True)
class ClaimedJob:
	id: str
	type: str
	payload_reference: str
	lease_token: str
	attempt_count: int
	maximum_attempts: int


class Worker:
	def __init__(self, engine: AsyncEngine, settings: WorkerSettings) -> None:
		self._engine = engine
		self._settings = settings

	async def run(self) -> None:
		while True:
			worked = await self.run_once()
			if not worked:
				await asyncio.sleep(self._settings.poll_interval_seconds)

	async def run_once(self) -> bool:
		job = await self._claim()
		if job is None:
			return False
		try:
			await self._dispatch(job)
		except NonRetryableJobError as error:
			await self._fail(job, str(error), retryable=False)
		except Exception:
			logger.exception("processing job failed", extra={"job_id": job.id, "type": job.type})
			await self._fail(job, "Processing failed", retryable=True)
		else:
			await self._complete(job)
		return True

	async def _claim(self) -> ClaimedJob | None:
		lease_token = secrets.token_urlsafe(24)
		lease_expires_at = datetime.now(UTC) + timedelta(seconds=self._settings.lease_seconds)
		async with self._engine.begin() as connection:
			result = await connection.execute(
				text(
					"""
					SELECT id, type, payload_reference, attempt_count, maximum_attempts
					FROM processing_job
					WHERE (status = 'ready' AND available_at <= now())
						OR (status = 'processing' AND lease_expires_at < now())
					ORDER BY available_at, created_at
					FOR UPDATE SKIP LOCKED
					LIMIT 1
					"""
				)
			)
			row = result.mappings().one_or_none()
			if row is None:
				return None
			await connection.execute(
				text(
					"""
					UPDATE processing_job
					SET status = 'processing', lease_token = :lease_token,
						lease_expires_at = :lease_expires_at,
						attempt_count = attempt_count + 1, updated_at = now()
					WHERE id = :id
					"""
				),
				{"id": row["id"], "lease_token": lease_token, "lease_expires_at": lease_expires_at},
			)
			return ClaimedJob(
				id=str(row["id"]),
				type=str(row["type"]),
				payload_reference=str(row["payload_reference"]),
				lease_token=lease_token,
				attempt_count=int(row["attempt_count"]) + 1,
				maximum_attempts=int(row["maximum_attempts"]),
			)

	async def _dispatch(self, job: ClaimedJob) -> None:
		if job.type == "evaluation_processing":
			await self._prepare_evaluation(job)
			return
		if job.type != "resume_processing":
			raise NonRetryableJobError("Unsupported processing job type")
		async with self._engine.connect() as connection:
			result = await connection.execute(
				text(
					"""
					SELECT document.storage_key, document.media_type
					FROM resume_version AS version
					JOIN resume_document AS document ON document.id = version.resume_document_id
					WHERE version.id = :version_id
					"""
				),
				{"version_id": job.payload_reference},
			)
			row = result.mappings().one_or_none()
		if row is None:
			raise NonRetryableJobError("Resume version not found")
		content = self._read_object(str(row["storage_key"]))
		try:
			blocks = extract_blocks(content, str(row["media_type"]))
		except DocumentParseError as error:
			raise NonRetryableJobError(str(error)) from error
		async with self._engine.begin() as connection:
			normalized_facts = normalize_resume(blocks["blocks"])
			await connection.execute(
				text(
					"""
					UPDATE resume_version
					SET extraction_blocks = CAST(:blocks AS jsonb),
						normalized_facts = CAST(:normalized_facts AS jsonb),
						quality_state = 'ready',
						parser_version = 'local-1'
					WHERE id = :version_id
						AND EXISTS (
							SELECT 1 FROM processing_job
							WHERE id = :job_id AND lease_token = :lease_token
								AND lease_expires_at > now()
						)
					"""
				),
				{
					"blocks": json.dumps(blocks),
					"normalized_facts": json.dumps(normalized_facts),
					"version_id": job.payload_reference,
					"job_id": job.id,
					"lease_token": job.lease_token,
				},
			)
			result = await connection.execute(
				text("SELECT id FROM evaluation WHERE resume_version_id = :resume_version_id"),
				{"resume_version_id": job.payload_reference},
			)
			for evaluation_id in result.scalars():
				await connection.execute(
					text(
						"""
						INSERT INTO processing_job (
							id, type, status, payload_reference, idempotency_key,
							attempt_count, maximum_attempts, available_at, created_at, updated_at
						) VALUES (
							:id, 'evaluation_processing', 'ready', :evaluation_id, :evaluation_id,
							0, 3, now(), now(), now()
						)
						ON CONFLICT (type, idempotency_key) DO NOTHING
						"""
					),
					{"id": secrets.token_urlsafe(18), "evaluation_id": evaluation_id},
				)

	def _read_object(self, key: str) -> bytes:
		root = self._settings.storage_root.resolve()
		path = (root / key).resolve()
		if root not in path.parents or not path.is_file():
			raise NonRetryableJobError("Resume source document is unavailable")
		return path.read_bytes()

	async def _prepare_evaluation(self, job: ClaimedJob) -> None:
		async with self._engine.begin() as connection:
			result = await connection.execute(
				text(
					"""
					SELECT evaluation.resume_version_id, version.normalized_facts
					FROM evaluation
					JOIN resume_version AS version ON version.id = evaluation.resume_version_id
					WHERE evaluation.id = :evaluation_id
					"""
				),
				{"evaluation_id": job.payload_reference},
			)
			evaluation = result.mappings().one_or_none()
			if evaluation is None:
				raise NonRetryableJobError("Evaluation not found")
			requirements = await connection.execute(
				text(
					"""
					SELECT requirement.id, requirement.kind, requirement.weight,
						requirement.normalized_text
					FROM evaluation
					JOIN job_requirement AS requirement
						ON requirement.job_version_id = evaluation.job_version_id
					WHERE evaluation.id = :evaluation_id
					"""
				),
				{"evaluation_id": job.payload_reference},
			)
			outcome = evaluate(
				dict(evaluation["normalized_facts"] or {}),
				[dict(requirement) for requirement in requirements.mappings().all()],
			)
			for assessment in outcome.assessments:
				await connection.execute(
					text(
						"""
						INSERT INTO requirement_assessment (
							id, evaluation_id, job_requirement_id, outcome, confidence,
							reasoning, evidence, created_at
						) VALUES (
							:id, :evaluation_id, :job_requirement_id, :outcome,
							:confidence, :reasoning,
							CAST(:evidence AS jsonb), now()
						)
						ON CONFLICT (evaluation_id, job_requirement_id) DO NOTHING
						"""
					),
					{
						"id": secrets.token_urlsafe(18),
						"evaluation_id": job.payload_reference,
						"job_requirement_id": assessment.requirement_id,
						"outcome": assessment.outcome,
						"confidence": assessment.confidence,
						"reasoning": assessment.reasoning,
						"evidence": json.dumps(assessment.evidence),
					},
				)
			await connection.execute(
				text(
					"""
					UPDATE evaluation
					SET status = 'complete', score = :score, evidence_coverage = :coverage,
						eligibility = :eligibility, quality_state = 'ready', completed_at = now()
					WHERE id = :evaluation_id
						AND EXISTS (
							SELECT 1 FROM processing_job
							WHERE id = :job_id AND lease_token = :lease_token
								AND lease_expires_at > now()
						)
					"""
				),
				{
					"evaluation_id": job.payload_reference,
					"job_id": job.id,
					"lease_token": job.lease_token,
					"score": outcome.score,
					"coverage": outcome.evidence_coverage,
					"eligibility": outcome.eligibility,
				},
			)

	async def _complete(self, job: ClaimedJob) -> None:
		await self._update_job(job, "completed", None, None)

	async def _fail(self, job: ClaimedJob, error: str, retryable: bool) -> None:
		if retryable and job.attempt_count < job.maximum_attempts:
			delay = min(300, 2**job.attempt_count) + random.uniform(0, 1)
			available_at = datetime.now(UTC) + timedelta(seconds=delay)
			await self._update_job(job, "ready", error, available_at)
			return
		await self._update_job(job, "dead", error, None)

	async def _update_job(
		self, job: ClaimedJob, status: str, safe_error: str | None, available_at: datetime | None
	) -> None:
		async with self._engine.begin() as connection:
			await connection.execute(
				text(
					"""
					UPDATE processing_job
					SET status = :status, safe_error = :safe_error,
						available_at = COALESCE(:available_at, available_at),
						lease_token = NULL, lease_expires_at = NULL, updated_at = now()
					WHERE id = :id AND lease_token = :lease_token
					"""
				),
				{
					"id": job.id,
					"lease_token": job.lease_token,
					"status": status,
					"safe_error": safe_error,
					"available_at": available_at,
				},
			)


async def main() -> None:
	logging.basicConfig(level=logging.INFO)
	settings = load_settings()
	engine = create_async_engine(settings.database_url, pool_pre_ping=True)
	try:
		await Worker(engine, settings).run()
	finally:
		await engine.dispose()


if __name__ == "__main__":
	asyncio.run(main())
