
import asyncio
import json
import logging
import random
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import WorkerSettings, load_settings
from .documents.normalizer import normalize_resume
from .documents.parser import DocumentParseError, extract_blocks
from .documents.renderer import render_resume_docx
from .evaluations.evaluator import Assessment, evaluate, refine_assessments, summarize
from .evaluations.independent import independent_report
from .evaluations.semantic import text_hash, top_semantic_matches
from .extraction.extractor import (
	assess_requirements,
	extract_resume_facts,
	merge_facts,
	merge_suggestions,
)
from .providers.openrouter import OpenRouterClient, OpenRouterError

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
		self._openrouter = (
			OpenRouterClient(
				api_key=settings.openrouter.api_key or "",
				base_url=settings.openrouter.base_url,
				timeout_seconds=settings.openrouter.timeout_seconds,
			)
			if settings.llm_enabled
			else None
		)

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
		if job.type == "independent_evaluation_processing":
			await self._process_independent_evaluation(job)
			return
		if job.type == "evaluation_processing":
			await self._prepare_evaluation(job)
			return
		if job.type != "resume_processing":
			raise NonRetryableJobError("Unsupported processing job type")
		async with self._engine.connect() as connection:
			result = await connection.execute(
				text(
					"""
					SELECT document.storage_key, document.media_type, document.original_name
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
		block_list = blocks["blocks"]
		normalized_facts = normalize_resume(block_list)
		if self._openrouter is not None:
			try:
				extracted = await extract_resume_facts(
					self._openrouter,
					model=self._settings.openrouter.extraction_model,
					blocks=block_list,
					max_output_tokens=self._settings.openrouter.max_output_tokens,
					document=(
						str(row["original_name"]),
						content,
						str(row["media_type"]),
					),
				)
			except OpenRouterError as error:
				logger.warning(
					"model extraction failed; using deterministic facts",
					extra={"job_id": job.id, "reason": str(error)},
				)
			else:
				normalized_facts = merge_facts(normalized_facts, extracted, block_list)
		await self._store_parsed_resume(
			job, blocks=blocks, normalized_facts=normalized_facts
		)

	async def _store_parsed_resume(
		self,
		job: ClaimedJob,
		*,
		blocks: Mapping[str, object],
		normalized_facts: Mapping[str, object],
	) -> None:
		async with self._engine.begin() as connection:
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
			contact = normalized_facts["contact"]
			if not isinstance(contact, Mapping):
				raise NonRetryableJobError("Resume contact facts are invalid")
			await connection.execute(
				text(
					"""
					UPDATE candidate_record AS candidate
					SET full_name = COALESCE(candidate.full_name, :name),
						email = COALESCE(candidate.email, :email),
						location = COALESCE(candidate.location, :location), updated_at = now()
					FROM resume_submission AS submission
					WHERE submission.candidate_record_id = candidate.id
						AND submission.resume_version_id = :version_id
					"""
				),
				{
					"name": contact["name"],
					"email": contact["email"],
					"location": contact["location"],
					"version_id": job.payload_reference,
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
		await self._store_block_embeddings(job)

	async def _store_block_embeddings(self, job: ClaimedJob) -> None:
		if self._openrouter is None:
			return
		model = self._settings.openrouter.embedding_model
		async with self._engine.connect() as connection:
			result = await connection.execute(
				text(
					"""
					SELECT block->>'id' AS block_id, block->>'text' AS block_text
					FROM resume_version, jsonb_array_elements(extraction_blocks->'blocks') AS block
					WHERE id = :version_id
					"""
				),
				{"version_id": job.payload_reference},
			)
			rows = result.mappings().all()
		texts_by_block: dict[str, str] = {}
		hashes_by_block: dict[str, str] = {}
		for row in rows:
			block_text = str(row["block_text"] or "").strip()
			if not block_text:
				continue
			block_id = str(row["block_id"])
			texts_by_block[block_id] = block_text
			hashes_by_block[block_id] = text_hash(block_text)
		if not texts_by_block:
			return
		unique_hashes = sorted(set(hashes_by_block.values()))
		async with self._engine.begin() as connection:
			cached = await connection.execute(
				text(
					"SELECT text_hash, vector FROM embedding_cache "
					"WHERE model = :model AND text_hash = ANY(:hashes)"
				),
				{"model": model, "hashes": unique_hashes},
			)
			vectors_by_hash = {
				str(row["text_hash"]): list(row["vector"])
				for row in cached.mappings()
			}
		missing_texts: dict[str, str] = {}
		for block_id, block_hash in hashes_by_block.items():
			if block_hash not in vectors_by_hash:
				missing_texts.setdefault(block_hash, texts_by_block[block_id])
		if missing_texts:
			try:
				vectors = await self._openrouter.embed_texts(
					model=model, texts=list(missing_texts.values())
				)
			except OpenRouterError as error:
				logger.warning(
					"embedding failed; skipping semantic evidence",
					extra={"job_id": job.id, "reason": str(error)},
				)
				return
			for block_hash, vector in zip(missing_texts.keys(), vectors):
				vectors_by_hash[block_hash] = vector
			async with self._engine.begin() as connection:
				for block_hash, vector in vectors_by_hash.items():
					if block_hash in missing_texts:
						await connection.execute(
							text(
								"""
								INSERT INTO embedding_cache (model, text_hash, vector)
								VALUES (:model, :text_hash, CAST(:vector AS jsonb))
								ON CONFLICT (model, text_hash) DO NOTHING
								"""
							),
							{
								"model": model,
								"text_hash": block_hash,
								"vector": json.dumps(vector),
							},
						)
		async with self._engine.begin() as connection:
			for block_id, block_hash in hashes_by_block.items():
				vector = vectors_by_hash.get(block_hash)
				if vector is None:
					continue
				await connection.execute(
					text(
						"""
						INSERT INTO resume_block_embedding (
							resume_version_id, block_id, model, text_hash, vector
						) VALUES (:version_id, :block_id, :model, :text_hash,
							CAST(:vector AS jsonb))
						ON CONFLICT (resume_version_id, block_id, model) DO UPDATE
							SET vector = EXCLUDED.vector, created_at = now()
						"""
					),
					{
						"version_id": job.payload_reference,
						"block_id": block_id,
						"model": model,
						"text_hash": block_hash,
						"vector": json.dumps(vector),
					},
				)

	async def _process_independent_evaluation(self, job: ClaimedJob) -> None:
		async with self._engine.begin() as connection:
			result = await connection.execute(
				text(
					"""
					UPDATE independent_evaluation
					SET status = 'processing', safe_error = NULL
					WHERE id = :evaluation_id
					RETURNING storage_key, media_type, original_name, job_description
					"""
				),
				{"evaluation_id": job.payload_reference},
			)
			evaluation = result.mappings().one_or_none()
		if evaluation is None:
			raise NonRetryableJobError("Independent evaluation not found")
		content = self._read_object(str(evaluation["storage_key"]))
		try:
			blocks = extract_blocks(content, str(evaluation["media_type"]))
		except DocumentParseError as error:
			raise NonRetryableJobError(str(error)) from error
		block_list = blocks["blocks"]
		normalized_facts = normalize_resume(block_list)
		job_description = (
			str(evaluation["job_description"]) if evaluation["job_description"] else None
		)
		if self._openrouter is not None:
			try:
				extracted = await extract_resume_facts(
					self._openrouter,
					model=self._settings.openrouter.extraction_model,
					blocks=block_list,
					max_output_tokens=self._settings.openrouter.max_output_tokens,
					document=(
						str(evaluation["original_name"]),
						content,
						str(evaluation["media_type"]),
					),
				)
			except OpenRouterError as error:
				logger.warning(
					"model extraction failed; using deterministic facts",
					extra={"job_id": job.id, "reason": str(error)},
				)
			else:
				facts = merge_facts(normalized_facts, extracted, block_list)
				score, suggestions = independent_report(facts, job_description)
				extra_suggestions = cast(
					list[dict[str, object]], extracted.get("suggestions") or []
				)
				await self._store_independent_report(
					job,
					evaluation_id=job.payload_reference,
					facts=facts,
					score=score,
					suggestions=merge_suggestions(suggestions, extra_suggestions),
				)
				return
		score, suggestions = independent_report(normalized_facts, job_description)
		await self._store_independent_report(
			job,
			evaluation_id=job.payload_reference,
			facts=normalized_facts,
			score=score,
			suggestions=suggestions,
		)

	async def _store_independent_report(
		self,
		job: ClaimedJob,
		*,
		evaluation_id: str,
		facts: Mapping[str, object],
		score: int,
		suggestions: list[dict[str, object]],
	) -> None:
		improved_key = f"independent-resumes/improved/{evaluation_id}.docx"
		try:
			document = render_resume_docx(facts, cast(list[Mapping[str, object]], suggestions))
		except Exception:
			logger.exception("corrected resume rendering failed", extra={"job_id": job.id})
			improved_key = None
		else:
			self._write_object(improved_key, document)
		async with self._engine.begin() as connection:
			await connection.execute(
				text(
					"""
					UPDATE independent_evaluation
					SET status = 'complete', score = :score,
						suggestions = CAST(:suggestions AS jsonb),
						normalized_facts = CAST(:normalized_facts AS jsonb),
						improved_resume_key = :improved_key,
						improved_resume_unlocked_at = now(),
						safe_error = NULL, completed_at = now()
					WHERE id = :evaluation_id
						AND EXISTS (
							SELECT 1 FROM processing_job
							WHERE id = :job_id AND lease_token = :lease_token
								AND lease_expires_at > now()
						)
					"""
				),
				{
					"evaluation_id": evaluation_id,
					"job_id": job.id,
					"lease_token": job.lease_token,
					"score": score,
					"suggestions": json.dumps(suggestions),
					"normalized_facts": json.dumps(dict(facts)),
					"improved_key": improved_key,
				},
			)

	def _read_object(self, key: str) -> bytes:
		path = self._object_path(key)
		if not path.is_file():
			raise NonRetryableJobError("Resume source document is unavailable")
		return path.read_bytes()

	def _write_object(self, key: str, content: bytes) -> None:
		path = self._object_path(key)
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_bytes(content)

	def _object_path(self, key: str) -> Path:
		root = self._settings.storage_root.resolve()
		path = (root / key).resolve()
		if root not in path.parents:
			raise NonRetryableJobError("Storage key escapes the configured root")
		return path

	async def _prepare_evaluation(self, job: ClaimedJob) -> None:
		async with self._engine.begin() as connection:
			result = await connection.execute(
				text(
					"""
					SELECT evaluation.resume_version_id, version.normalized_facts,
						version.extraction_blocks
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
			requirement_list = [dict(requirement) for requirement in requirements.mappings()]
			outcome = evaluate(dict(evaluation["normalized_facts"] or {}), requirement_list)
			assessments: Sequence[Assessment] = outcome.assessments
			if self._openrouter is not None and requirement_list:
				extraction_blocks = cast(
					Mapping[str, object],
					cast(object, evaluation["extraction_blocks"]) or {},
				)
				blocks = cast(list[Mapping[str, object]], extraction_blocks.get("blocks", []))
				try:
					model_assessments = await assess_requirements(
						self._openrouter,
						model=self._settings.openrouter.assessment_model,
						requirements=requirement_list,
						blocks=blocks,
						max_output_tokens=self._settings.openrouter.max_output_tokens,
					)
				except OpenRouterError as error:
					logger.warning(
						"model assessment failed; using deterministic outcomes",
						extra={"job_id": job.id, "reason": str(error)},
					)
				else:
					assessments = refine_assessments(
						assessments, model_assessments, requirement_list
					)
					outcome = summarize(assessments, requirement_list)
			semantic_evidence = await self._retrieve_semantic_evidence(
				job,
				version_id=str(evaluation["resume_version_id"]),
				requirements=requirement_list,
			)
			for assessment in outcome.assessments:
				await connection.execute(
					text(
						"""
						INSERT INTO requirement_assessment (
							id, evaluation_id, job_requirement_id, outcome, confidence,
							reasoning, evidence, semantic_evidence, created_at
						) VALUES (
							:id, :evaluation_id, :job_requirement_id, :outcome,
							:confidence, :reasoning,
							CAST(:evidence AS jsonb), CAST(:semantic AS jsonb), now()
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
						"semantic": json.dumps(
							semantic_evidence.get(assessment.requirement_id)
						),
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

	async def _retrieve_semantic_evidence(
		self,
		job: ClaimedJob,
		*,
		version_id: str,
		requirements: list[dict[str, object]],
	) -> dict[str, dict[str, object]]:
		if self._openrouter is None or not requirements:
			return {}
		model = self._settings.openrouter.embedding_model
		async with self._engine.connect() as connection:
			result = await connection.execute(
				text(
					"""
					SELECT block_id, vector FROM resume_block_embedding
					WHERE resume_version_id = :version_id AND model = :model
					"""
				),
				{"version_id": version_id, "model": model},
			)
			block_vectors = {
				str(row["block_id"]): [float(value) for value in row["vector"]]
				for row in result.mappings()
			}
		if not block_vectors:
			return {}
		try:
			vectors = await self._openrouter.embed_texts(
				model=model,
				texts=[str(requirement["normalized_text"]) for requirement in requirements],
			)
		except OpenRouterError as error:
			logger.warning(
				"requirement embedding failed; no semantic evidence",
				extra={"job_id": job.id, "reason": str(error)},
			)
			return {}
		retrieved: dict[str, dict[str, object]] = {}
		for requirement, vector in zip(requirements, vectors):
			matches = top_semantic_matches(vector, block_vectors)
			if matches:
				retrieved[str(requirement["id"])] = {"model": model, "matches": matches}
		return retrieved

	async def _complete(self, job: ClaimedJob) -> None:
		await self._update_job(job, "completed", None, None)

	async def _fail(self, job: ClaimedJob, error: str, retryable: bool) -> None:
		if retryable and job.attempt_count < job.maximum_attempts:
			delay = min(300, 2**job.attempt_count) + random.uniform(0, 1)
			available_at = datetime.now(UTC) + timedelta(seconds=delay)
			await self._update_job(job, "ready", error, available_at)
			return
		await self._update_job(job, "dead", error, None)
		if job.type == "independent_evaluation_processing":
			async with self._engine.begin() as connection:
				await connection.execute(
					text(
						"""
						UPDATE independent_evaluation
						SET status = 'failed', safe_error = :safe_error
						WHERE id = :evaluation_id
						"""
					),
					{"evaluation_id": job.payload_reference, "safe_error": error},
				)

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
