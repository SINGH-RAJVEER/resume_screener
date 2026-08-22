from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import ValidationError

from ..documents.vocabulary import load_vocabulary
from ..providers.openrouter import OpenRouterClient, OpenRouterError, document_file_part
from .prompt import ASSESSMENT_SYSTEM_PROMPT, EXTRACTION_SYSTEM_PROMPT
from .schemas import (
	RESUME_FACTS_SCHEMA_VERSION,
	AssessmentOutput,
	RequirementOutcome,
	ResumeExtraction,
	strict_schema,
)


def blocks_document(blocks: Sequence[Mapping[str, object]]) -> str:
	return "\n\n".join(
		f"[{block['id']}]\n{block['text']}"
		for block in blocks
		if str(block.get("text", "")).strip()
	)


async def extract_resume_facts(
	client: OpenRouterClient,
	*,
	model: str,
	blocks: Sequence[Mapping[str, object]],
	max_output_tokens: int = 4096,
	document: tuple[str, bytes, str] | None = None,
) -> dict[str, object]:
	parts: list[dict[str, object]] = [
		{
			"type": "text",
			"text": "<resume_document>\n" + blocks_document(blocks) + "\n</resume_document>",
		}
	]
	if document is not None:
		filename, content, media_type = document
		file_part = document_file_part(filename, content, media_type)
		if file_part is not None:
			parts.append(file_part)
	raw = await client.complete_json(
		model=model,
		system_prompt=EXTRACTION_SYSTEM_PROMPT,
		user_parts=parts,
		schema_name="resume_facts",
		schema=strict_schema(ResumeExtraction),
		max_output_tokens=max_output_tokens,
	)
	return validate_extraction(raw, {str(block["id"]) for block in blocks})


def validate_extraction(raw: dict[str, object], block_ids: set[str]) -> dict[str, object]:
	try:
		extraction = ResumeExtraction.model_validate(raw)
	except ValidationError as error:
		raise OpenRouterError("Model extraction does not match the schema") from error
	facts = extraction.model_dump(by_alias=True)
	facts["skills"] = [
		pruned
		for skill in facts["skills"]
		if (pruned := prune_skill(cast(dict[str, object], skill), block_ids)) is not None
	]
	dropped = len(extraction.skills) - len(facts["skills"])
	if dropped:
		facts["warnings"] = [
			*cast(list[str], facts["warnings"]),
			f"{dropped} skills lacked valid evidence",
		]
	facts["schemaVersion"] = RESUME_FACTS_SCHEMA_VERSION
	return facts


async def assess_requirements(
	client: OpenRouterClient,
	*,
	model: str,
	requirements: Sequence[Mapping[str, object]],
	blocks: Sequence[Mapping[str, object]],
	max_output_tokens: int = 4096,
) -> list[dict[str, object]]:
	requirement_lines = "\n".join(
		f"- id: {requirement['id']} | text: {requirement.get('normalized_text', '')}"
		for requirement in requirements
	)
	parts: list[dict[str, object]] = [
		{
			"type": "text",
			"text": "<job_requirements>\n" + requirement_lines + "\n</job_requirements>",
		},
		{
			"type": "text",
			"text": "<resume_document>\n" + blocks_document(list(blocks)) + "\n</resume_document>",
		},
	]
	raw = await client.complete_json(
		model=model,
		system_prompt=ASSESSMENT_SYSTEM_PROMPT,
		user_parts=parts,
		schema_name="requirement_assessments",
		schema=strict_schema(AssessmentOutput),
		max_output_tokens=max_output_tokens,
	)
	return validate_assessments(
		raw,
		{str(requirement["id"]) for requirement in requirements},
		{str(block["id"]) for block in blocks},
	)


def validate_assessments(
	raw: dict[str, object], requirement_ids: set[str], block_ids: set[str]
) -> list[dict[str, object]]:
	try:
		output = AssessmentOutput.model_validate(raw)
	except ValidationError as error:
		raise OpenRouterError("Model assessment does not match the schema") from error
	valid: list[dict[str, object]] = []
	for assessment in output.assessments:
		if assessment.requirement_id not in requirement_ids:
			continue
		entry = assessment.model_dump(by_alias=True)
		entry["evidence"] = [
			item
			for item in entry["evidence"]
			if str(cast(dict[str, object], item).get("blockId", "")) in block_ids
		]
		if (
			RequirementOutcome(entry["outcome"]) is not RequirementOutcome.UNKNOWN
			and not entry["evidence"]
		):
			# Confirmed outcomes require evidence; unsupported confirmations
			# degrade to unknown rather than being dropped.
			entry["outcome"] = RequirementOutcome.UNKNOWN.value
			entry["confidence"] = min(float(entry["confidence"]), 0.5)
		valid.append(entry)
	return valid


def prune_skill(
	skill: dict[str, object], block_ids: set[str]
) -> dict[str, object] | None:
	entries = cast(list[object], skill.get("evidence") or [])
	valid = [
		cast(dict[str, object], entry)
		for entry in entries
		if isinstance(entry, dict)
		and str(cast(dict[str, object], entry).get("blockId", "")) in block_ids
	]
	if not valid:
		return None
	return {**skill, "evidence": valid}


def merge_facts(
	normalized_facts: Mapping[str, object],
	extracted_facts: Mapping[str, object],
	blocks: Sequence[Mapping[str, object]],
) -> dict[str, object]:
	vocabulary = load_vocabulary()
	deterministic_skills = {
		str(skill.get("canonicalName")): skill for skill in _entries(normalized_facts.get("skills"))
	}
	merged: dict[str, dict[str, object]] = {}
	for name, skill in deterministic_skills.items():
		merged[name.casefold()] = {
			"canonicalName": name,
			"category": skill.get("category"),
			"evidenceBlockIds": skill.get("evidenceBlockIds", []),
		}
	for skill in _entries(extracted_facts.get("skills")):
		source = str(skill.get("canonicalName", "")).strip()
		if not source or source.casefold() in merged:
			continue
		canonical = vocabulary.phrase_to_canonical.get(source.casefold(), source)
		key = canonical.casefold()
		if key in merged:
			continue
		block_references = sorted(
			{
				str(entry.get("blockId"))
				for entry in _entries(skill.get("evidence"))
				if entry.get("blockId")
			},
			key=block_order(blocks),
		)
		merged[key] = {
			"canonicalName": canonical,
			"category": vocabulary.categories.get(canonical.casefold()),
			"evidenceBlockIds": block_references,
		}
	contact = _mapping(normalized_facts.get("contact"))
	extracted_contact = _mapping(extracted_facts.get("contact"))
	merged_contact = {
		key: contact.get(key) or extracted_contact.get(key)
		for key in ("name", "email", "phone", "location")
	}
	return {
		"contact": merged_contact,
		"skills": sorted(merged.values(), key=lambda skill: str(skill["canonicalName"]).casefold()),
		"employment": _entries(extracted_facts.get("employment")),
		"education": _entries(extracted_facts.get("education")),
		"certifications": _entries(extracted_facts.get("certifications")),
		"warnings": _strings(extracted_facts.get("warnings")),
	}


def block_order(blocks: Sequence[Mapping[str, object]]):
	order = {str(block["id"]): index for index, block in enumerate(blocks)}

	def key(block_id: str) -> int:
		return order.get(block_id, len(order))

	return key


def merge_suggestions(
	deterministic: Sequence[Mapping[str, object]],
	extracted: Sequence[Mapping[str, object]],
	limit: int = 10,
) -> list[dict[str, object]]:
	merged: dict[str, dict[str, object]] = {}
	for suggestion in [*deterministic, *extracted]:
		title = str(suggestion.get("title", "")).strip()
		if title and title.casefold() not in merged:
			merged[title.casefold()] = {"title": title, "detail": suggestion.get("detail")}
	return list(merged.values())[:limit]


def _mapping(value: object) -> Mapping[str, object]:
	if isinstance(value, Mapping):
		return cast(Mapping[str, object], value)
	return {}


def _entries(value: object) -> list[dict[str, object]]:
	if not isinstance(value, list):
		return []
	return [
		cast(dict[str, object], item) for item in cast(list[object], value)
		if isinstance(item, dict)
	]


def _strings(value: object) -> list[str]:
	if not isinstance(value, list):
		return []
	return [item for item in cast(list[object], value) if isinstance(item, str)]
