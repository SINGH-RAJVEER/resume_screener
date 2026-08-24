import json
from typing import cast

import httpx
import pytest

from worker.extraction.extractor import (
	blocks_document,
	extract_resume_facts,
	merge_facts,
	merge_suggestions,
	validate_extraction,
)
from worker.providers.openrouter import OpenRouterClient, OpenRouterError


def test_blocks_document_labels_each_block() -> None:
	document = blocks_document([{"id": "p1-b1", "text": "Ada\nada@example.com"}])
	assert document == "[p1-b1]\nAda\nada@example.com"


async def test_extractor_sends_only_bounded_evidence_text() -> None:
	requests: list[dict[str, object]] = []

	def handler(request: httpx.Request) -> httpx.Response:
		requests.append(cast(dict[str, object], json.loads(request.content)))
		return httpx.Response(
			200,
			json={
				"choices": [
					{
						"finish_reason": "stop",
						"message": {"content": json.dumps(raw_extraction())},
					}
				]
			},
		)

	client = OpenRouterClient(api_key="key", transport=httpx.MockTransport(handler))
	await extract_resume_facts(
		client,
		model="model",
		blocks=[
			{
				"id": "p1-b1",
				"text": (
					"Ada Lovelace\nada@example.com\nPython services\n"
					"Engineer at Example Corp"
				),
			}
		],
	)

	payload = requests[0]
	serialized = json.dumps(payload)
	assert "file_data" not in serialized
	assert "data:application/pdf" not in serialized
	assert "[p1-b1]" in serialized


def raw_extraction() -> dict[str, object]:
	return {
		"schemaVersion": "2",
		"contact": {
			"name": "Ada Lovelace",
			"email": "ada@example.com",
			"phone": None,
			"location": "The Moon",
			"evidence": [
				{"blockId": "p1-b1", "quote": "Ada Lovelace\nada@example.com"}
			],
		},
		"skills": [
			{
				"canonicalName": "Python",
				"sourceText": "Python services",
				"evidence": [{"blockId": "p1-b1", "quote": "Python services"}],
			},
			{
				"canonicalName": "Fabricated block",
				"sourceText": "invented",
				"evidence": [{"blockId": "p9-b9", "quote": "no such block"}],
			},
			{
				"canonicalName": "Fabricated quote",
				"sourceText": "invented",
				"evidence": [{"blockId": "p1-b1", "quote": "not in the block"}],
			},
		],
		"employment": [
			{
				"employer": "Example Corp",
				"title": "Engineer",
				"startDate": "2022-03",
				"endDate": None,
				"isCurrent": True,
				"evidence": [
					{"blockId": "p1-b1", "quote": "Engineer at Example Corp"}
				],
			}
		],
		"education": [],
		"certifications": [
			{
				"name": "Imaginary certification",
				"issuer": None,
				"evidence": [{"blockId": "p1-b1", "quote": "not in the block"}],
			}
		],
		"suggestions": [
			{"title": "Quantify outcomes", "detail": "Add measured results."}
		],
		"warnings": [],
	}


def test_validate_extraction_drops_facts_without_exact_source_evidence() -> None:
	facts = validate_extraction(
		raw_extraction(),
		{
			"p1-b1": (
				"Ada Lovelace\nada@example.com\nPython services\nEngineer at Example Corp"
			)
		},
	)
	skills = cast(list[dict[str, object]], facts["skills"])
	assert [skill["canonicalName"] for skill in skills] == ["Python"]
	assert facts["certifications"] == []
	contact = cast(dict[str, object], facts["contact"])
	assert contact["name"] == "Ada Lovelace"
	assert contact["email"] == "ada@example.com"
	assert contact["location"] is None
	warnings = cast(list[str], facts["warnings"])
	assert "2 skills lacked valid evidence" in warnings
	assert "1 certifications lacked valid evidence" in warnings
	assert "1 contact fields lacked source evidence" in warnings


def test_validate_extraction_rejects_schema_violations() -> None:
	raw = raw_extraction()
	raw["employment"] = [{"employer": 42, "title": None, "isCurrent": True}]
	with pytest.raises(OpenRouterError):
		validate_extraction(raw, {"p1-b1": "Example Corp"})


def normalized_facts() -> dict[str, object]:
	return {
		"contact": {"name": None, "email": "deterministic@example.com", "location": None},
		"skills": [
			{
				"canonicalName": "PostgreSQL",
				"category": "Databases",
				"evidenceBlockIds": ["p1-b2"],
			}
		],
	}


def test_merge_facts_unions_and_normalizes_skill_names() -> None:
	extracted = validate_extraction(
		raw_extraction(),
		{
			"p1-b1": (
				"Ada Lovelace\nada@example.com\nPython services\nEngineer at Example Corp"
			)
		},
	)
	blocks: list[dict[str, object]] = [
		{
			"id": "p1-b1",
			"text": "Ada Lovelace\nada@example.com\nPython services\nEngineer at Example Corp",
		},
		{"id": "p1-b2", "text": "y"},
	]
	facts = merge_facts(normalized_facts(), extracted, blocks)
	skills = cast(list[dict[str, object]], facts["skills"])
	names = [skill["canonicalName"] for skill in skills]
	assert names == ["PostgreSQL", "Python"]
	python = skills[1]
	assert python["evidenceBlockIds"] == ["p1-b1"]
	contact = cast(dict[str, object], facts["contact"])
	assert contact["email"] == "deterministic@example.com"
	assert contact["name"] == "Ada Lovelace"
	assert contact.get("phone") is None
	employment = cast(list[object], facts["employment"])
	assert len(employment) == 1


def test_merge_suggestions_dedupes_by_title_and_caps() -> None:
	deterministic: list[dict[str, object]] = [
		{"title": "Add a clear name", "detail": "Start with your name."}
	]
	extracted: list[dict[str, object]] = [
		{"title": "add a clear name", "detail": "duplicate"},
		{"title": "Quantify outcomes", "detail": "Add measured results."},
	]
	merged = merge_suggestions(deterministic, extracted)
	assert merged == [
		{"title": "Add a clear name", "detail": "Start with your name."},
		{"title": "Quantify outcomes", "detail": "Add measured results."},
	]
	repeated: list[dict[str, object]] = [
		{"title": f"t{i}", "detail": "d"} for i in range(20)
	]
	assert len(merge_suggestions(repeated, [])) == 10
