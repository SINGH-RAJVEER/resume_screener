from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import ValidationError

from ..documents.vocabulary import load_vocabulary
from ..providers.openrouter import OpenRouterClient, OpenRouterError
from .prompt import ASSESSMENT_SYSTEM_PROMPT, EXTRACTION_SYSTEM_PROMPT
from .schemas import (
	RESUME_FACTS_SCHEMA_VERSION,
	AssessmentOutput,
	RequirementOutcome,
	ResumeExtraction,
	strict_schema,
)

EVIDENCE_TEXT_FIELDS = {
	"skills": ("sourceText",),
	"employment": ("employer", "title"),
	"education": ("institution", "degree", "fieldOfStudy"),
	"certifications": ("name", "issuer"),
	"suggestions": (),
}


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
) -> dict[str, object]:
	parts: list[dict[str, object]] = [
		{
			"type": "text",
			"text": "<resume_document>\n" + blocks_document(blocks) + "\n</resume_document>",
		}
	]
	raw = await client.complete_json(
		model=model,
		system_prompt=EXTRACTION_SYSTEM_PROMPT,
		user_parts=parts,
		schema_name="resume_facts",
		schema=strict_schema(ResumeExtraction),
		max_output_tokens=max_output_tokens,
	)
	return validate_extraction(
		raw,
		{str(block["id"]): str(block.get("text", "")) for block in blocks},
	)


def validate_extraction(
	raw: dict[str, object], block_texts: Mapping[str, str]
) -> dict[str, object]:
	try:
		extraction = ResumeExtraction.model_validate(raw)
	except ValidationError as error:
		raise OpenRouterError("Model extraction does not match the schema") from error
	facts = extraction.model_dump(by_alias=True)
	warnings = cast(list[str], facts["warnings"])
	for field, text_fields in EVIDENCE_TEXT_FIELDS.items():
		entries = cast(list[object], facts[field])
		grounded = [
			validated
			for item in entries
			if isinstance(item, dict)
			and (
				validated := validate_fact_evidence(
					cast(dict[str, object], item), block_texts, text_fields
				)
			)
			is not None
		]
		facts[field] = grounded
		dropped = len(entries) - len(grounded)
		if dropped:
			warnings.append(f"{dropped} {field} lacked valid evidence")
	facts["contact"], dropped_contact_fields = validate_contact_evidence(
		cast(dict[str, object], facts["contact"]), block_texts
	)
	if dropped_contact_fields:
		warnings.append(f"{dropped_contact_fields} contact fields lacked source evidence")
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
		{
			str(block["id"]): str(block.get("text", ""))
			for block in blocks
		},
	)


def validate_assessments(
	raw: dict[str, object],
	requirement_ids: set[str],
	block_texts: Mapping[str, str],
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
			if valid_evidence_quote(cast(dict[str, object], item), block_texts)
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


def valid_evidence_quote(
	evidence: Mapping[str, object], block_texts: Mapping[str, str]
) -> bool:
	block_id = str(evidence.get("blockId", ""))
	quote = str(evidence.get("quote", ""))
	return bool(quote) and quote in block_texts.get(block_id, "")


def validate_fact_evidence(
	fact: dict[str, object],
	block_texts: Mapping[str, str],
	text_fields: Sequence[str] = (),
) -> dict[str, object] | None:
	evidence = [
		cast(dict[str, object], entry)
		for entry in cast(list[object], fact.get("evidence") or [])
		if isinstance(entry, dict)
		and valid_evidence_quote(cast(dict[str, object], entry), block_texts)
	]
	if not evidence:
		return None
	evidence_text = "\n".join(str(entry.get("quote", "")) for entry in evidence).casefold()
	if any(
		isinstance(value := fact.get(field), str)
		and value.strip()
		and value.casefold() not in evidence_text
		for field in text_fields
	):
		return None
	return {**fact, "evidence": evidence}


def validate_contact_evidence(
	contact: dict[str, object], block_texts: Mapping[str, str]
) -> tuple[dict[str, object], int]:
	grounded = validate_fact_evidence(contact, block_texts)
	valid_evidence = cast(list[dict[str, object]], grounded.get("evidence", [])) if grounded else []
	cited_text = "\n".join(str(evidence.get("quote", "")) for evidence in valid_evidence)
	dropped = 0
	result = {**contact, "evidence": valid_evidence}
	for field in ("name", "email", "phone", "location"):
		value = result.get(field)
		if value is None:
			continue
		if str(value).casefold() not in cited_text.casefold():
			result[field] = None
			dropped += 1
	return result, dropped


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
