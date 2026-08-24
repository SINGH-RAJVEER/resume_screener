import time
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from worker import main as worker_main
from worker.config import OpenRouterSettings, WorkerSettings
from worker.documents.parser import DocumentParseError
from worker.documents.processing import add_document_warnings, prepare_document
from worker.main import NonRetryableJobError, Worker, extract_document_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_prepares_ready_evidence_and_deterministic_facts() -> None:
	prepared = prepare_document(
		(FIXTURES / "single_column_resume.txt").read_bytes(),
		"text/plain",
	)

	assert prepared.quality_state == "ready"
	assert prepared.warnings == []
	assert prepared.artifact["metadata"]["blockCount"] == 3
	assert prepared.normalized_facts["warnings"] == []


def test_carries_parser_warnings_into_normalized_facts() -> None:
	prepared = prepare_document(b"Ada Lovelace", "text/plain")

	assert prepared.quality_state == "review_required"
	assert prepared.warnings == ["Document contains very little extractable text"]
	assert prepared.normalized_facts["warnings"] == prepared.warnings


def test_instruction_like_resume_requires_review_before_normalization_is_scored() -> None:
	prepared = prepare_document(
		(FIXTURES / "prompt_injection_resume.txt").read_bytes(),
		"text/plain",
	)

	assert prepared.quality_state == "review_required"
	assert "instruction-like text" in prepared.warnings[0]


def test_review_required_document_cannot_supply_automated_job_text() -> None:
	with pytest.raises(DocumentParseError, match="could not be read reliably"):
		extract_document_text(b"Short description", "text/plain")


def test_parser_warnings_survive_model_fact_merging() -> None:
	facts = add_document_warnings(
		{"warnings": ["Model omitted one unsupported fact"]},
		["One page contained no extractable text"],
	)

	assert facts["warnings"] == [
		"One page contained no extractable text",
		"Model omitted one unsupported fact",
	]


def bounded_settings(parse_timeout_seconds: float = 0.05) -> WorkerSettings:
	return WorkerSettings(
		database_url="postgresql+asyncpg://worker:secret@db/skillsignal",
		storage_root=Path(".local-storage"),
		poll_interval_seconds=1,
		lease_seconds=60,
		parse_timeout_seconds=parse_timeout_seconds,
		openrouter=OpenRouterSettings(
			api_key=None,
			base_url="https://openrouter.ai/api/v1",
			extraction_model="m",
			assessment_model="m",
			embedding_model="e",
			timeout_seconds=5,
			max_output_tokens=1024,
		),
	)


async def test_worker_bounds_document_preparation_time(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def slow_prepare(content: bytes, media_type: str) -> object:
		time.sleep(0.2)
		raise AssertionError("parsing should have been cancelled")

	monkeypatch.setattr(worker_main, "prepare_document", slow_prepare)
	worker = Worker(engine=cast("AsyncEngine", None), settings=bounded_settings())

	with pytest.raises(NonRetryableJobError, match="time limit"):
		await worker._prepare_bounded(b"content", "text/plain")  # pyright: ignore[reportPrivateUsage]


async def test_worker_bounds_document_text_extraction_time(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	def slow_extract(content: bytes, media_type: str) -> str:
		time.sleep(0.2)
		raise AssertionError("extraction should have been cancelled")

	monkeypatch.setattr(worker_main, "extract_document_text", slow_extract)
	worker = Worker(engine=cast("AsyncEngine", None), settings=bounded_settings())

	with pytest.raises(NonRetryableJobError, match="time limit"):
		await worker._extract_text_bounded(b"content", "text/plain")  # pyright: ignore[reportPrivateUsage]
