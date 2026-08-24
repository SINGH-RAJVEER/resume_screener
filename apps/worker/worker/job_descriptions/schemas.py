from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..versions import (
	JOB_REQUIREMENTS_COMPILER_VERSION,
	JOB_REQUIREMENTS_PROMPT_VERSION,
	JOB_REQUIREMENTS_SCHEMA_VERSION,
)

__all__ = [
	"JOB_REQUIREMENTS_COMPILER_VERSION",
	"JOB_REQUIREMENTS_PROMPT_VERSION",
	"JOB_REQUIREMENTS_SCHEMA_VERSION",
]


class SchemaModel(BaseModel):
	model_config = ConfigDict(
		extra="forbid",
		strict=True,
		alias_generator=to_camel,
		populate_by_name=True,
	)


class RequirementCategory(StrEnum):
	SKILL = "skill"
	EXPERIENCE = "experience"
	EDUCATION = "education"
	CERTIFICATION = "certification"
	LANGUAGE = "language"
	LOCATION = "location"
	WORK_AUTHORIZATION = "work_authorization"
	SCHEDULE = "schedule"
	SOFT_SKILL = "soft_skill"
	OTHER = "other"


class SuggestedKind(StrEnum):
	REQUIRED = "required"
	PREFERRED = "preferred"
	IGNORED = "ignored"


class SourceModality(StrEnum):
	EXPLICIT_REQUIRED = "explicit_required"
	EXPLICIT_PREFERRED = "explicit_preferred"
	SECTION_REQUIRED = "section_required"
	SECTION_PREFERRED = "section_preferred"
	UNCLEAR = "unclear"


class Assessability(StrEnum):
	RESUME_EVIDENCE = "resume_evidence"
	CANDIDATE_ATTESTATION = "candidate_attestation"
	RECRUITER_REVIEW = "recruiter_review"
	PROHIBITED = "prohibited"
	UNCLEAR = "unclear"


class PredicateOperator(StrEnum):
	ALL_OF = "all_of"
	ANY_OF = "any_of"


class CriterionType(StrEnum):
	SKILL = "skill"
	EXPERIENCE = "experience"
	EDUCATION = "education"
	CERTIFICATION = "certification"
	OTHER = "other"


class ModelEvidenceQuote(SchemaModel):
	block_id: str = Field(min_length=1, max_length=128)
	quote: str = Field(min_length=1, max_length=2_000)


class PredicateCriterion(SchemaModel):
	type: CriterionType = Field(strict=False)
	canonical_name: str | None = Field(default=None, max_length=256)
	minimum_months: int | None = Field(default=None, ge=0, le=1_200)
	minimum_level: str | None = Field(default=None, max_length=64)
	subjects: list[str] = Field(default=[], max_length=20)


class RequirementPredicate(SchemaModel):
	operator: PredicateOperator = Field(strict=False)
	criteria: list[PredicateCriterion] = Field(min_length=1, max_length=30)


class ModelRequirementDraft(SchemaModel):
	normalized_text: str = Field(min_length=3, max_length=2_000)
	category: RequirementCategory = Field(strict=False)
	suggested_kind: SuggestedKind = Field(strict=False)
	source_modality: SourceModality = Field(strict=False)
	assessability: Assessability = Field(strict=False)
	predicate: RequirementPredicate
	evidence: list[ModelEvidenceQuote] = Field(min_length=1, max_length=10)
	confidence: float = Field(ge=0, le=1)


class ModelRequirementExtraction(SchemaModel):
	requirements: list[ModelRequirementDraft] = Field(max_length=100)
	warnings: list[str] = Field(default=[], max_length=50)
