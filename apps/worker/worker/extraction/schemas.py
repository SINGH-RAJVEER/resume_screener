"""Versioned strict contracts for model-extracted resume facts.

Field names mirror `apps/api/app/extraction_schemas.py` so stored artifacts
stay comparable across the API and worker deployables.
"""

from enum import StrEnum
from typing import cast

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..versions import (
	EXTRACTION_PROMPT_VERSION,
	REQUIREMENT_ASSESSMENT_SCHEMA_VERSION,
	RESUME_FACTS_SCHEMA_VERSION,
)

__all__ = [
	"EXTRACTION_PROMPT_VERSION",
	"REQUIREMENT_ASSESSMENT_SCHEMA_VERSION",
	"RESUME_FACTS_SCHEMA_VERSION",
]

DATE_PATTERN = r"^\d{4}(-\d{2})?$"


class SchemaModel(BaseModel):
	model_config = ConfigDict(
		extra="forbid",
		strict=True,
		alias_generator=to_camel,
		populate_by_name=True,
	)


class EvidenceQuote(SchemaModel):
	block_id: str = Field(min_length=1, max_length=128)
	quote: str = Field(min_length=1, max_length=2_000)


class ContactFacts(SchemaModel):
	name: str | None = Field(default=None, max_length=256)
	email: str | None = Field(default=None, max_length=320)
	phone: str | None = Field(default=None, max_length=64)
	location: str | None = Field(default=None, max_length=256)


class SkillFact(SchemaModel):
	canonical_name: str = Field(min_length=1, max_length=128)
	source_text: str = Field(min_length=1, max_length=1_000)
	evidence: list[EvidenceQuote] = Field(min_length=1, max_length=20)


class EmploymentFact(SchemaModel):
	employer: str | None = Field(default=None, max_length=256)
	title: str | None = Field(default=None, max_length=256)
	start_date: str | None = Field(default=None, pattern=DATE_PATTERN)
	end_date: str | None = Field(default=None, pattern=DATE_PATTERN)
	is_current: bool


class EducationFact(SchemaModel):
	institution: str | None = Field(default=None, max_length=256)
	degree: str | None = Field(default=None, max_length=256)
	field_of_study: str | None = Field(default=None, max_length=256)
	graduation_date: str | None = Field(default=None, pattern=DATE_PATTERN)


class CertificationFact(SchemaModel):
	name: str = Field(min_length=1, max_length=256)
	issuer: str | None = Field(default=None, max_length=256)


class Suggestion(SchemaModel):
	title: str = Field(min_length=1, max_length=200)
	detail: str = Field(min_length=1, max_length=1_000)


class RequirementOutcome(StrEnum):
	MET = "met"
	PARTIAL = "partial"
	NOT_MET = "not_met"
	UNKNOWN = "unknown"


class AssessedRequirement(SchemaModel):
	requirement_id: str = Field(min_length=1, max_length=128)
	# Strict mode would demand an enum instance; model output arrives as text.
	outcome: RequirementOutcome = Field(strict=False)
	confidence: float = Field(ge=0, le=1)
	reasoning: str = Field(min_length=1, max_length=2_000)
	evidence: list[EvidenceQuote] = Field(default=[], max_length=20)


class AssessmentOutput(SchemaModel):
	assessments: list[AssessedRequirement] = Field(max_length=200)


class ResumeExtraction(SchemaModel):
	schema_version: str = RESUME_FACTS_SCHEMA_VERSION
	contact: ContactFacts
	skills: list[SkillFact] = Field(max_length=200)
	employment: list[EmploymentFact] = Field(max_length=100)
	education: list[EducationFact] = Field(max_length=50)
	certifications: list[CertificationFact] = Field(max_length=100)
	suggestions: list[Suggestion] = Field(default=[], max_length=10)
	warnings: list[str] = Field(default=[], max_length=50)


def strict_schema(model: type[BaseModel]) -> dict[str, object]:
	# Strict structured outputs require every property in `required` and no
	# additional properties anywhere; optional fields are nullable instead.
	schema = _tighten(model.model_json_schema())
	return cast(dict[str, object], schema)


def _tighten(node: object) -> object:
	if isinstance(node, dict):
		tightened_map: dict[str, object] = {
			key: _tighten(value) for key, value in cast(dict[str, object], node).items()
		}
		properties = tightened_map.get("properties")
		if isinstance(properties, dict):
			tightened_map["required"] = list(cast(dict[str, object], properties).keys())
			tightened_map["additionalProperties"] = False
		return tightened_map
	if isinstance(node, list):
		return [_tighten(item) for item in cast(list[object], node)]
	return node
