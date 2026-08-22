from typing import cast

import pytest

from worker.extraction.extractor import (
	blocks_document,
	merge_facts,
	merge_suggestions,
	validate_extraction,
)
from worker.providers.openrouter import OpenRouterError


def test_blocks_document_labels_each_block() -> None:
	document = blocks_document([{"id": "p1-b1", "text": "Ada\nada@example.com"}])
	assert document == "[p1-b1]\nAda\nada@example.com"


def raw_extraction() -> dict[str, object]:
	return {
		"schemaVersion": "1",
		"contact": {
			"name": "Ada Lovelace",
			"email": "ada@example.com",
			"phone": None,
			"location": "London",
		},
		"skills": [
			{
				"canonicalName": "Python",
				"sourceText": "Python services",
				"evidence": [{"blockId": "p1-b1", "quote": "Python services"}],
			},
			{
				"canonicalName": "Fabricated",
				"sourceText": "invented",
				"evidence": [{"blockId": "p9-b9", "quote": "no such block"}],
			},
		],
		"employment": [
			{
				"employer": "Example Corp",
				"title": "Engineer",
				"startDate": "2022-03",
				"endDate": None,
				"isCurrent": True,
			}
		],
		"education": [],
		"certifications": [],
		"suggestions": [
			{"title": "Quantify outcomes", "detail": "Add measured results."}
		],
		"warnings": [],
	}


def test_validate_extraction_drops_skills_without_valid_blocks() -> None:
	facts = validate_extraction(raw_extraction(), {"p1-b1"})
	skills = cast(list[dict[str, object]], facts["skills"])
	assert [skill["canonicalName"] for skill in skills] == ["Python"]
	warnings = cast(list[str], facts["warnings"])
	assert any("lacked valid evidence" in warning for warning in warnings)


def test_validate_extraction_rejects_schema_violations() -> None:
	raw = raw_extraction()
	raw["employment"] = [{"employer": 42, "title": None, "isCurrent": True}]
	with pytest.raises(OpenRouterError):
		validate_extraction(raw, {"p1-b1"})


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
	extracted = validate_extraction(raw_extraction(), {"p1-b1"})
	blocks: list[dict[str, object]] = [
		{"id": "p1-b1", "text": "x"},
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
