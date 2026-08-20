"""Versioned, strict contracts for extracted resume and evaluation data."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

RESUME_FACTS_SCHEMA_VERSION = "1"
JOB_REQUIREMENTS_SCHEMA_VERSION = "1"
REQUIREMENT_ASSESSMENT_SCHEMA_VERSION = "1"
SCORING_POLICY_VERSION = "1"


class SchemaModel(BaseModel):
	model_config = ConfigDict(
		extra="forbid",
		strict=True,
		alias_generator=to_camel,
		populate_by_name=True,
	)


class EvidenceReference(SchemaModel):
	block_id: str = Field(min_length=1, max_length=128)
	quote: str = Field(min_length=1, max_length=2_000)


class ContactFacts(SchemaModel):
	email: str | None = Field(default=None, max_length=320)
	phone: str | None = Field(default=None, max_length=64)
	location: str | None = Field(default=None, max_length=256)
	links: list[str] = Field(default_factory=list, max_length=20)
	evidence: list[EvidenceReference] = Field(default=[], max_length=20)


class IdentityFacts(SchemaModel):
	full_name: str | None = Field(default=None, max_length=256)
	evidence: list[EvidenceReference] = Field(default=[], max_length=10)


class SkillFact(SchemaModel):
	canonical_name: str = Field(min_length=1, max_length=128)
	source_text: str = Field(min_length=1, max_length=1_000)
	evidence: list[EvidenceReference] = Field(min_length=1, max_length=20)


class EmploymentFact(SchemaModel):
	employer: str | None = Field(default=None, max_length=256)
	title: str | None = Field(default=None, max_length=256)
	start_date: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2})?$")
	end_date: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2})?$")
	is_current: bool
	description: str | None = Field(default=None, max_length=8_000)
	evidence: list[EvidenceReference] = Field(min_length=1, max_length=50)


class ProjectFact(SchemaModel):
	name: str = Field(min_length=1, max_length=256)
	description: str | None = Field(default=None, max_length=8_000)
	evidence: list[EvidenceReference] = Field(min_length=1, max_length=50)


class EducationFact(SchemaModel):
	institution: str | None = Field(default=None, max_length=256)
	degree: str | None = Field(default=None, max_length=256)
	field_of_study: str | None = Field(default=None, max_length=256)
	graduation_date: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2})?$")
	evidence: list[EvidenceReference] = Field(min_length=1, max_length=20)


class CertificationFact(SchemaModel):
	name: str = Field(min_length=1, max_length=256)
	issuer: str | None = Field(default=None, max_length=256)
	issued_date: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2})?$")
	expires_date: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2})?$")
	evidence: list[EvidenceReference] = Field(min_length=1, max_length=20)


class ExtractionWarning(SchemaModel):
	code: str = Field(min_length=1, max_length=64)
	message: str = Field(min_length=1, max_length=1_000)
	evidence: list[EvidenceReference] = Field(default=[], max_length=20)


class ResumeFacts(SchemaModel):
	schema_version: str = RESUME_FACTS_SCHEMA_VERSION
	identity: IdentityFacts | None = None
	contact: ContactFacts | None = None
	skills: list[SkillFact] = Field(max_length=200)
	employment: list[EmploymentFact] = Field(max_length=100)
	projects: list[ProjectFact] = Field(max_length=100)
	education: list[EducationFact] = Field(max_length=50)
	certifications: list[CertificationFact] = Field(max_length=100)
	warnings: list[ExtractionWarning] = Field(max_length=100)


class RequirementKind(StrEnum):
	REQUIRED = "required"
	PREFERRED = "preferred"
	IGNORED = "ignored"
	HARD_GATE = "hard_gate"


class RequirementImportance(StrEnum):
	LOW = "low"
	MEDIUM = "medium"
	HIGH = "high"


class JobRequirementDraft(SchemaModel):
	stable_id: str = Field(min_length=1, max_length=128)
	category: str = Field(min_length=1, max_length=128)
	normalized_text: str = Field(min_length=1, max_length=2_000)
	suggested_importance: RequirementImportance
	source_evidence: list[EvidenceReference] = Field(min_length=1, max_length=20)


class ConfirmedJobRequirement(JobRequirementDraft):
	kind: RequirementKind
	weight: int | None = Field(default=None, gt=0, le=100)
	aliases: list[str] = Field(default_factory=list, max_length=50)

	@model_validator(mode="after")
	def apply_default_weight(self) -> ConfirmedJobRequirement:
		if self.weight is None:
			self.weight = 2 if self.kind is RequirementKind.REQUIRED else 1
		return self


class JobRequirements(SchemaModel):
	schema_version: str = JOB_REQUIREMENTS_SCHEMA_VERSION
	requirements: list[JobRequirementDraft] = Field(max_length=200)


class AssessmentOutcome(StrEnum):
	MET = "met"
	PARTIAL = "partial"
	NOT_MET = "not_met"
	UNKNOWN = "unknown"


class RequirementAssessment(SchemaModel):
	requirement_id: str = Field(min_length=1, max_length=128)
	outcome: AssessmentOutcome
	confidence: float = Field(ge=0, le=1)
	reasoning: str = Field(min_length=1, max_length=2_000)
	evidence: list[EvidenceReference] = Field(default=[], max_length=20)
	warnings: list[ExtractionWarning] = Field(default=[], max_length=20)

	@model_validator(mode="after")
	def confirmed_outcomes_have_evidence(self) -> RequirementAssessment:
		if self.outcome is not AssessmentOutcome.UNKNOWN and not self.evidence:
			raise ValueError("confirmed outcomes require evidence")
		return self


class ScoreComponents(SchemaModel):
	deterministic: float = Field(ge=0, le=1)
	semantic: float = Field(ge=0, le=1)
	assessment: float = Field(ge=0, le=1)


class AssessmentResult(SchemaModel):
	schema_version: str = REQUIREMENT_ASSESSMENT_SCHEMA_VERSION
	scoring_policy_version: str = SCORING_POLICY_VERSION
	assessments: list[RequirementAssessment] = Field(max_length=200)
	score_components: ScoreComponents | None = None
