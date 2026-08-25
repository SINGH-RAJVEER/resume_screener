import asyncio
import json
import logging
import random
import secrets
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from opentelemetry.trace import Status, StatusCode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .billing import (
	release_evaluation_reservations,
	settle_points,
	settle_reservation,
)
from .config import WorkerSettings, load_settings
from .documents.parser import DocumentParseError
from .documents.processing import (
	PreparedDocument,
	add_document_warnings,
	prepare_document,
)
from .documents.renderer import render_resume_docx
from .evaluations.evaluator import Assessment, evaluate, refine_assessments, summarize
from .evaluations.independent import independent_report
from .evaluations.lexical import top_lexical_matches
from .evaluations.semantic import text_hash, top_semantic_matches
from .extraction.extractor import (
	assess_requirements,
	extract_resume_facts,
	merge_facts,
	merge_suggestions,
)
from .job_descriptions.compiler import compile_job_description
from .job_descriptions.extractor import extract_job_requirements
from .providers.openrouter import OpenRouterClient, OpenRouterError
from .telemetry import (
	instrument_engine,
	instrument_httpx_clients,
	record_job_outcome,
	setup_telemetry,
	shutdown_telemetry,
	tracer,
)
from .versions import (
	ASSESSMENT_PROMPT_VERSION,
	EXTRACTION_PROMPT_VERSION,
	JOB_REQUIREMENTS_COMPILER_VERSION,
	JOB_REQUIREMENTS_PROMPT_VERSION,
	LOCAL_PARSER_VERSION,
	PARSER_CONFIGURATION_VERSION,
	REQUIREMENT_ASSESSMENT_SCHEMA_VERSION,
	RESUME_FACTS_SCHEMA_VERSION,
	SCORING_POLICY_VERSION,
)

logger = logging.getLogger("skillsignal.worker")
DETERMINISTIC_EXTRACTION_WARNING = (
	"Structured extraction was unavailable; only deterministic facts were used"
)


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


def extract_document_text(content: bytes, media_type: str) -> str:
	prepared = prepare_document(content, media_type)
	if prepared.quality_state != "ready":
		raise DocumentParseError(document_quality_error("Document", prepared.warnings))
	texts: list[str] = []
	for raw_block in cast(list[object], prepared.blocks):
		if not isinstance(raw_block, Mapping):
			continue
		block = cast(Mapping[str, object], raw_block)
		texts.append(str(block.get("text", "")).strip())
	return "\n\n".join(text for text in texts if text)


def document_quality_error(label: str, warnings: Sequence[str]) -> str:
	detail = "; ".join(warnings) if warnings else "Extraction quality was too low"
	return f"{label} could not be read reliably. {detail}. Upload a clearer digital document"


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
		started = time.monotonic()
		outcome = "completed"
		if self._openrouter is not None:
			self._openrouter.reset_usage()
		with tracer.start_as_current_span(
			"process_job",
			attributes={
				"skillsignal.job.id": job.id,
				"skillsignal.job.type": job.type,
				"skillsignal.job.attempt": job.attempt_count,
			},
		) as span:
			try:
				await self._dispatch(job)
			except NonRetryableJobError as error:
				span.set_status(Status(StatusCode.ERROR, str(error)))
				await self._fail(job, str(error), retryable=False)
				outcome = "failed_non_retryable"
			except Exception as error:
				logger.exception(
					"processing job failed", extra={"job_id": job.id, "type": job.type}
				)
				span.record_exception(error)
				span.set_status(Status(StatusCode.ERROR, "Processing failed"))
				await self._fail(job, "Processing failed", retryable=True)
				outcome = "failed"
			else:
				await self._complete(job)
		record_job_outcome(job.type, outcome, time.monotonic() - started)
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
		if job.type == "job_description_processing":
			await self._process_job_description(job)
			return
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
			prepared = await self._prepare_bounded(content, str(row["media_type"]))
		except DocumentParseError as error:
			raise NonRetryableJobError(str(error)) from error
		block_list = prepared.blocks
		normalized_facts = prepared.normalized_facts
		extracted_facts: Mapping[str, object] | None = None
		if prepared.quality_state == "ready" and self._openrouter is None:
			normalized_facts = add_document_warnings(
				normalized_facts, [DETERMINISTIC_EXTRACTION_WARNING]
			)
		elif prepared.quality_state == "ready" and self._openrouter is not None:
			try:
					extracted = await extract_resume_facts(
						self._openrouter,
						model=self._settings.openrouter.extraction_model,
						blocks=block_list,
						max_output_tokens=self._settings.openrouter.max_output_tokens,
					)
			except OpenRouterError as error:
				logger.warning(
					"model extraction failed; using deterministic facts",
					extra={"job_id": job.id, "reason": str(error)},
				)
				normalized_facts = add_document_warnings(
					normalized_facts, [DETERMINISTIC_EXTRACTION_WARNING]
				)
			else:
				extracted_facts = extracted
				normalized_facts = add_document_warnings(
					merge_facts(normalized_facts, extracted, block_list),
					prepared.warnings,
				)
		stored = await self._store_parsed_resume(
			job,
			blocks=prepared.artifact,
			structured_facts=extracted_facts,
			normalized_facts=normalized_facts,
			quality_state=prepared.quality_state,
		)
		if not stored or prepared.quality_state != "ready":
			return
		await self._store_block_embeddings(job)
		await self._queue_evaluations(job)

	async def _store_parsed_resume(
		self,
		job: ClaimedJob,
		*,
		blocks: Mapping[str, object],
		structured_facts: Mapping[str, object] | None,
		normalized_facts: Mapping[str, object],
		quality_state: str,
	) -> bool:
		async with self._engine.begin() as connection:
			result = await connection.execute(
				text(
					"""
					UPDATE resume_version
					SET extraction_blocks = CAST(:blocks AS jsonb),
						structured_facts = CAST(:structured_facts AS jsonb),
						normalized_facts = CAST(:normalized_facts AS jsonb),
						quality_state = :quality_state,
						parser_version = :parser_version,
						parser_configuration_version = :parser_configuration_version,
						schema_version = :schema_version,
						extraction_prompt_version = :extraction_prompt_version
					WHERE id = :version_id
						AND EXISTS (
							SELECT 1 FROM processing_job
							WHERE id = :job_id AND lease_token = :lease_token
								AND lease_expires_at > now()
						)
					RETURNING id
					"""
				),
				{
					"blocks": json.dumps(blocks),
					"structured_facts": json.dumps(dict(structured_facts or {})),
					"normalized_facts": json.dumps(normalized_facts),
					"quality_state": quality_state,
					"parser_version": LOCAL_PARSER_VERSION,
					"parser_configuration_version": PARSER_CONFIGURATION_VERSION,
					"schema_version": RESUME_FACTS_SCHEMA_VERSION,
					"extraction_prompt_version": (
						EXTRACTION_PROMPT_VERSION if structured_facts is not None else None
					),
					"version_id": job.payload_reference,
					"job_id": job.id,
					"lease_token": job.lease_token,
				},
			)
			if result.scalar_one_or_none() is None:
				return False
			if quality_state != "ready":
				await connection.execute(
					text(
						"""
						UPDATE evaluation
						SET status = 'complete', score = NULL, evidence_coverage = NULL,
							eligibility = 'needs_review', quality_state = :quality_state,
							completed_at = now()
						WHERE resume_version_id = :version_id
						"""
					),
					{"quality_state": quality_state, "version_id": job.payload_reference},
				)
				# Parsing and review delivery happened even without scoring,
				# so employer holds settle at the minimum charge.
				holds = await connection.execute(
					text(
						"""
						SELECT id FROM point_reservation
						WHERE state = 'reserved' AND id IN (
							SELECT point_reservation_id FROM evaluation
							WHERE resume_version_id = :version_id
								AND point_reservation_id IS NOT NULL
						)
						"""
					),
					{"version_id": job.payload_reference},
				)
				for hold in holds.scalars():
					await settle_reservation(
						connection,
						str(hold),
						self._settings.billing.minimum_employer_resume_points,
						"Employer resume charge (review required)",
					)
				return True
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
		return True

	async def _queue_evaluations(self, job: ClaimedJob) -> None:
		async with self._engine.begin() as connection:
			result = await connection.execute(
				text(
					"""
					SELECT evaluation.id
					FROM evaluation
					WHERE evaluation.resume_version_id = :resume_version_id
						AND EXISTS (
							SELECT 1 FROM processing_job
							WHERE id = :job_id AND lease_token = :lease_token
								AND lease_expires_at > now()
						)
					"""
				),
				{
					"resume_version_id": job.payload_reference,
					"job_id": job.id,
					"lease_token": job.lease_token,
				},
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

	async def _process_job_description(self, job: ClaimedJob) -> None:
		async with self._engine.connect() as connection:
			result = await connection.execute(
				text(
					"""
					SELECT source_text, source_storage_key, source_media_type
					FROM job_version
					WHERE id = :version_id
					"""
				),
				{"version_id": job.payload_reference},
			)
			version_row = result.mappings().one_or_none()
		if version_row is None:
			raise NonRetryableJobError("Job version not found")
		source_storage_key = version_row["source_storage_key"]
		if source_storage_key:
			content = self._read_object(str(source_storage_key))
			try:
				source = await self._extract_text_bounded(
					content, str(version_row["source_media_type"])
				)
			except DocumentParseError as error:
				raise NonRetryableJobError(str(error)) from error
		elif version_row["source_text"] is not None:
			source = str(version_row["source_text"])
		else:
			raise NonRetryableJobError("Job description is unavailable")
		if self._openrouter is None:
			artifact = compile_job_description(
				source,
				degraded=True,
				degraded_reason=(
					"Model extraction was unavailable; deterministic drafts require careful review"
				),
			)
		else:
			try:
				model_output = await extract_job_requirements(
					self._openrouter,
					model=self._settings.openrouter.extraction_model,
					source_text=source,
					max_output_tokens=self._settings.openrouter.max_output_tokens,
				)
			except OpenRouterError as error:
				logger.warning(
					"job requirement extraction failed; using deterministic drafts",
					extra={"job_id": job.id, "reason": str(error)},
				)
				artifact = compile_job_description(
					source,
					degraded=True,
					degraded_reason=(
						"Model extraction failed; deterministic drafts require careful review"
					),
				)
			else:
				artifact = compile_job_description(source, model_output)
		async with self._engine.begin() as connection:
			await connection.execute(
				text(
					"""
					UPDATE job_version
					SET draft_requirements = CAST(:artifact AS jsonb),
						source_text = :source_text,
						normalized_text = :normalized_text,
						schema_version = :schema_version,
						prompt_version = :prompt_version,
						compiler_version = :compiler_version
					WHERE id = :version_id
						AND EXISTS (
							SELECT 1 FROM processing_job
							WHERE id = :job_id AND lease_token = :lease_token
								AND lease_expires_at > now()
						)
					"""
				),
				{
					"artifact": json.dumps(artifact),
					"source_text": source,
					"normalized_text": source.strip(),
					"schema_version": str(artifact["schemaVersion"]),
					"prompt_version": JOB_REQUIREMENTS_PROMPT_VERSION,
					"compiler_version": JOB_REQUIREMENTS_COMPILER_VERSION,
					"version_id": job.payload_reference,
					"job_id": job.id,
					"lease_token": job.lease_token,
				},
			)

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
				str(row["text_hash"]): list(row["vector"]) for row in cached.mappings()
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
					RETURNING storage_key, media_type, original_name, job_description,
						job_description_key, job_description_media_type
					"""
				),
				{"evaluation_id": job.payload_reference},
			)
			evaluation = result.mappings().one_or_none()
		if evaluation is None:
			raise NonRetryableJobError("Independent evaluation not found")
		content = self._read_object(str(evaluation["storage_key"]))
		try:
			prepared = await self._prepare_bounded(content, str(evaluation["media_type"]))
		except DocumentParseError as error:
			raise NonRetryableJobError(str(error)) from error
		if prepared.quality_state != "ready":
			raise NonRetryableJobError(
				document_quality_error("Resume", prepared.warnings)
			)
		block_list = prepared.blocks
		normalized_facts = prepared.normalized_facts
		description_key = evaluation["job_description_key"]
		if description_key:
			try:
				job_description = await self._extract_text_bounded(
					self._read_object(str(description_key)),
					str(evaluation["job_description_media_type"]),
				)
			except DocumentParseError as error:
				raise NonRetryableJobError(str(error)) from error
		else:
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
					)
			except OpenRouterError as error:
				logger.warning(
					"model extraction failed; using deterministic facts",
					extra={"job_id": job.id, "reason": str(error)},
				)
				normalized_facts = add_document_warnings(
					normalized_facts, [DETERMINISTIC_EXTRACTION_WARNING]
				)
			else:
				facts = add_document_warnings(
					merge_facts(normalized_facts, extracted, block_list),
					prepared.warnings,
				)
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
					model_extraction_used=True,
					job_description_text=job_description,
				)
				return
		else:
			normalized_facts = add_document_warnings(
				normalized_facts, [DETERMINISTIC_EXTRACTION_WARNING]
			)
		score, suggestions = independent_report(normalized_facts, job_description)
		await self._store_independent_report(
			job,
			evaluation_id=job.payload_reference,
			facts=normalized_facts,
			score=score,
			suggestions=suggestions,
			model_extraction_used=False,
			job_description_text=job_description,
		)

	async def _store_independent_report(
		self,
		job: ClaimedJob,
		*,
		evaluation_id: str,
		facts: Mapping[str, object],
		score: int,
		suggestions: list[dict[str, object]],
		model_extraction_used: bool,
		job_description_text: str | None,
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
			result = await connection.execute(
				text(
					"""
					UPDATE independent_evaluation
					SET status = 'complete', score = :score,
						suggestions = CAST(:suggestions AS jsonb),
						normalized_facts = CAST(:normalized_facts AS jsonb),
						job_description = COALESCE(job_description, :job_description),
						improved_resume_key = :improved_key,
						improved_resume_unlocked_at = now(),
						parser_version = :parser_version,
						parser_configuration_version = :parser_configuration_version,
						schema_version = :schema_version,
						extraction_prompt_version = :extraction_prompt_version,
						scoring_policy_version = :scoring_policy_version,
						safe_error = NULL, completed_at = now()
					WHERE id = :evaluation_id
						AND EXISTS (
							SELECT 1 FROM processing_job
							WHERE id = :job_id AND lease_token = :lease_token
								AND lease_expires_at > now()
						)
					RETURNING point_reservation_id, free_week_start
					"""
				),
				{
					"evaluation_id": evaluation_id,
					"job_id": job.id,
					"lease_token": job.lease_token,
					"score": score,
					"suggestions": json.dumps(suggestions),
					"normalized_facts": json.dumps(dict(facts)),
					"job_description": job_description_text,
					"improved_key": improved_key,
					"parser_version": LOCAL_PARSER_VERSION,
					"parser_configuration_version": PARSER_CONFIGURATION_VERSION,
					"schema_version": RESUME_FACTS_SCHEMA_VERSION,
					"extraction_prompt_version": (
						EXTRACTION_PROMPT_VERSION if model_extraction_used else None
					),
					"scoring_policy_version": SCORING_POLICY_VERSION,
				},
			)
			billing_row = result.mappings().one_or_none()
			if billing_row is not None and billing_row["point_reservation_id"]:
				prompt_tokens, completion_tokens, cost_usd = self._model_usage()
				await settle_reservation(
					connection,
					str(billing_row["point_reservation_id"]),
					settle_points(
						prompt_tokens,
						completion_tokens,
						cost_usd,
						"independent_evaluation",
						self._settings.billing,
					),
					"Independent evaluation charge",
				)

	def _model_usage(self) -> tuple[int, int, float]:
		if self._openrouter is None:
			return 0, 0, 0.0
		return self._openrouter.usage()

	async def _prepare_bounded(self, content: bytes, media_type: str) -> PreparedDocument:
		try:
			return await asyncio.wait_for(
				asyncio.to_thread(prepare_document, content, media_type),
				self._settings.parse_timeout_seconds,
			)
		except TimeoutError as error:
			raise NonRetryableJobError(
				"Document parsing exceeded the configured time limit"
			) from error

	async def _extract_text_bounded(self, content: bytes, media_type: str) -> str:
		try:
			return await asyncio.wait_for(
				asyncio.to_thread(extract_document_text, content, media_type),
				self._settings.parse_timeout_seconds,
			)
		except TimeoutError as error:
			raise NonRetryableJobError(
				"Document parsing exceeded the configured time limit"
			) from error

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
			await connection.execute(
				text(
					"""
					UPDATE batch_evaluation AS batch
					SET model_configuration = CAST(:model_configuration AS jsonb)
					FROM evaluation
					WHERE evaluation.id = :evaluation_id
						AND batch.id = evaluation.batch_evaluation_id
						AND batch.model_configuration = '{}'::jsonb
					"""
				),
				{
					"evaluation_id": job.payload_reference,
					"model_configuration": json.dumps(
						{
							"extractionModel": self._settings.openrouter.extraction_model,
							"assessmentModel": self._settings.openrouter.assessment_model,
							"embeddingModel": self._settings.openrouter.embedding_model,
							"llmEnabled": self._settings.llm_enabled,
						}
					),
				},
			)
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
						requirement.normalized_text, requirement.category,
						requirement.assessability, requirement.predicate
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
			model_assessment_used = False
			assessable_requirements = [
				requirement
				for requirement in requirement_list
				if requirement.get("assessability") == "resume_evidence"
				and requirement.get("kind") != "ignored"
			]
			extraction_blocks = cast(
				Mapping[str, object],
				cast(object, evaluation["extraction_blocks"]) or {},
			)
			blocks = cast(list[Mapping[str, object]], extraction_blocks.get("blocks", []))
			if self._openrouter is not None and assessable_requirements:
				try:
					model_assessments = await assess_requirements(
						self._openrouter,
						model=self._settings.openrouter.assessment_model,
						requirements=assessable_requirements,
						blocks=blocks,
						max_output_tokens=self._settings.openrouter.max_output_tokens,
					)
				except OpenRouterError as error:
					logger.warning(
						"model assessment failed; using deterministic outcomes",
						extra={"job_id": job.id, "reason": str(error)},
					)
				else:
					model_assessment_used = True
					assessments = refine_assessments(
						assessments, model_assessments, requirement_list
					)
					outcome = summarize(assessments, requirement_list)
			block_texts = {
				str(block["id"]): str(block.get("text", ""))
				for block in blocks
				if block.get("id")
			}
			semantic_evidence = await self._retrieve_semantic_evidence(
				job,
				version_id=str(evaluation["resume_version_id"]),
				requirements=requirement_list,
			)
			lexical_evidence = self._retrieve_lexical_evidence(
				requirements=requirement_list, block_texts=block_texts
			)
			for assessment in outcome.assessments:
				await connection.execute(
					text(
						"""
						INSERT INTO requirement_assessment (
							id, evaluation_id, job_requirement_id, outcome, confidence,
							reasoning, evidence, semantic_evidence, lexical_evidence, created_at
						) VALUES (
							:id, :evaluation_id, :job_requirement_id, :outcome,
							:confidence, :reasoning,
							CAST(:evidence AS jsonb), CAST(:semantic AS jsonb),
							CAST(:lexical AS jsonb), now()
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
						"semantic": json.dumps(semantic_evidence.get(assessment.requirement_id)),
						"lexical": json.dumps(lexical_evidence.get(assessment.requirement_id)),
					},
				)
			await connection.execute(
				text(
					"""
					UPDATE evaluation
					SET status = 'complete', score = :score, evidence_coverage = :coverage,
						eligibility = :eligibility, quality_state = 'ready',
						scoring_policy_version = :scoring_policy_version,
						assessment_schema_version = :assessment_schema_version,
						assessment_prompt_version = :assessment_prompt_version,
						completed_at = now()
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
					"scoring_policy_version": SCORING_POLICY_VERSION,
					"assessment_schema_version": (
						REQUIREMENT_ASSESSMENT_SCHEMA_VERSION if model_assessment_used else None
					),
					"assessment_prompt_version": (
						ASSESSMENT_PROMPT_VERSION if model_assessment_used else None
					),
				},
			)
			reservation = (
				await connection.execute(
					text(
						"SELECT point_reservation_id FROM evaluation "
						"WHERE id = :evaluation_id AND point_reservation_id IS NOT NULL"
					),
					{"evaluation_id": job.payload_reference},
				)
			).scalar_one_or_none()
			if reservation:
				prompt_tokens, completion_tokens, cost_usd = self._model_usage()
				await settle_reservation(
					connection,
					str(reservation),
					settle_points(
						prompt_tokens,
						completion_tokens,
						cost_usd,
						"employer_resume",
						self._settings.billing,
					),
					"Employer resume charge",
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

	def _retrieve_lexical_evidence(
		self,
		*,
		requirements: list[dict[str, object]],
		block_texts: Mapping[str, str],
	) -> dict[str, dict[str, object]]:
		if not requirements or not block_texts:
			return {}
		retrieved: dict[str, dict[str, object]] = {}
		for requirement in requirements:
			matches = top_lexical_matches(
				str(requirement.get("normalized_text") or ""), block_texts
			)
			if matches:
				retrieved[str(requirement["id"])] = {"matches": matches}
		return retrieved

	async def _complete(self, job: ClaimedJob) -> None:
		await self._update_job(job, "completed", None, None)

	async def _fail(self, job: ClaimedJob, error: str, retryable: bool) -> None:
		if retryable and job.attempt_count < job.maximum_attempts:
			delay = min(300, 2**job.attempt_count) + random.uniform(0, 1)
			available_at = datetime.now(UTC) + timedelta(seconds=delay)
			await self._update_job(job, "ready", error, available_at)
			return
		updated = await self._update_job(job, "dead", error, None)
		if not updated:
			return
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
				# Failed evaluations release the point hold and return a
				# consumed weekly free allowance so it can be used again.
				await connection.execute(
					text(
						"""
						UPDATE point_reservation SET state = 'released', updated_at = now()
						WHERE state = 'reserved'
							AND id = (
								SELECT point_reservation_id FROM independent_evaluation
								WHERE id = :evaluation_id
							)
						"""
					),
					{"evaluation_id": job.payload_reference},
				)
				await connection.execute(
					text(
						"""
						DELETE FROM weekly_free_use
						WHERE (user_id, week_start) IN (
							SELECT user_id, free_week_start FROM independent_evaluation
							WHERE id = :evaluation_id AND free_week_start IS NOT NULL
						)
						"""
					),
					{"evaluation_id": job.payload_reference},
				)
		elif job.type == "resume_processing":
			async with self._engine.begin() as connection:
				await connection.execute(
					text(
						"""
						UPDATE resume_version
						SET quality_state = CASE
							WHEN quality_state = 'pending' THEN 'failed'
							ELSE quality_state
						END
						WHERE id = :version_id
						"""
					),
					{"version_id": job.payload_reference},
				)
				await connection.execute(
					text(
						"""
						UPDATE evaluation
						SET status = 'failed', eligibility = 'needs_review',
							quality_state = CASE
								WHEN quality_state = 'pending' THEN 'failed'
								ELSE quality_state
							END,
							completed_at = now()
						WHERE resume_version_id = :version_id
						"""
					),
					{"version_id": job.payload_reference},
				)
				await release_evaluation_reservations(
					connection,
					"resume_version_id = :version_id",
					{"version_id": job.payload_reference},
				)
		elif job.type == "evaluation_processing":
			async with self._engine.begin() as connection:
				await connection.execute(
					text(
						"""
						UPDATE evaluation
						SET status = 'failed', eligibility = 'needs_review', completed_at = now()
						WHERE id = :evaluation_id
						"""
					),
					{"evaluation_id": job.payload_reference},
				)
				await release_evaluation_reservations(
					connection, "id = :evaluation_id", {"evaluation_id": job.payload_reference}
				)

	async def _update_job(
		self, job: ClaimedJob, status: str, safe_error: str | None, available_at: datetime | None
	) -> bool:
		async with self._engine.begin() as connection:
			result = await connection.execute(
				text(
					"""
					UPDATE processing_job
					SET status = :status, safe_error = :safe_error,
						available_at = COALESCE(:available_at, available_at),
						lease_token = NULL, lease_expires_at = NULL, updated_at = now()
					WHERE id = :id AND lease_token = :lease_token
					RETURNING id
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
			return result.scalar_one_or_none() is not None


async def main() -> None:
	logging.basicConfig(level=logging.INFO)
	settings = load_settings()
	telemetry_on = setup_telemetry()
	engine = create_async_engine(settings.database_url, pool_pre_ping=True)
	try:
		if telemetry_on:
			instrument_engine(engine)
			instrument_httpx_clients()
		await Worker(engine, settings).run()
	finally:
		await engine.dispose()
		shutdown_telemetry()


if __name__ == "__main__":
	asyncio.run(main())
