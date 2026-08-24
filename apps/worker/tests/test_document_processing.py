from pathlib import Path

import pytest

from worker.documents.parser import DocumentParseError
from worker.documents.processing import add_document_warnings, prepare_document
from worker.main import extract_document_text

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
