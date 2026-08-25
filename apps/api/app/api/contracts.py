from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ErrorCode(StrEnum):
	ALREADY_MEMBER = "ALREADY_MEMBER"
	APPLICATIONS_CLOSED = "APPLICATIONS_CLOSED"
	EMAIL_ALREADY_EXISTS = "EMAIL_ALREADY_EXISTS"
	FORBIDDEN = "FORBIDDEN"
	INSUFFICIENT_POINTS = "INSUFFICIENT_POINTS"
	INTERNAL_ERROR = "INTERNAL_ERROR"
	INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
	INVALID_DOCUMENT = "INVALID_DOCUMENT"
	INVALID_EMAIL_OR_PASSWORD = "INVALID_EMAIL_OR_PASSWORD"
	INVALID_PACK = "INVALID_PACK"
	INVALID_REQUEST = "INVALID_REQUEST"
	INVALID_SIGNATURE = "INVALID_SIGNATURE"
	INVITATION_REDEEMED = "INVITATION_REDEEMED"
	MEMBER_EXISTS = "MEMBER_EXISTS"
	NOT_FOUND = "NOT_FOUND"
	ORIGIN_NOT_ALLOWED = "ORIGIN_NOT_ALLOWED"
	OWNER_REQUIRED = "OWNER_REQUIRED"
	REQUIREMENTS_NOT_CONFIRMED = "REQUIREMENTS_NOT_CONFIRMED"
	RULE_EXISTS = "RULE_EXISTS"
	SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
	UNAUTHORIZED = "UNAUTHORIZED"


class ContractModel(BaseModel):
	model_config = ConfigDict(
		extra="forbid",
		strict=True,
		alias_generator=to_camel,
		populate_by_name=True,
	)


class ErrorResponse(ContractModel):
	code: ErrorCode
	message: str


class JobAcceptedResponse(ContractModel):
	id: str
	version_id: str
	processing_job_id: str


class ResumeSubmissionAcceptedResponse(ContractModel):
	processing_job_id: str
	submission_id: str
	evaluation_id: str
	batch_evaluation_id: str


class ResumeBatchItemResponse(ContractModel):
	name: str
	processing_job_id: str
	submission_id: str
	evaluation_id: str


class RejectedBatchItemResponse(ContractModel):
	name: str
	reason: str


class ResumeBatchAcceptedResponse(ContractModel):
	batch_evaluation_id: str | None
	accepted: list[ResumeBatchItemResponse]
	rejected: list[RejectedBatchItemResponse]


class IndependentEvaluationAcceptedResponse(ContractModel):
	id: str
	processing_job_id: str
	free_evaluation: bool = False
	reserved_points: int = 0


class ProcessingJobResponse(ContractModel):
	id: str
	status: str
	safe_error: str | None
	retryable: bool


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
	400: {"model": ErrorResponse, "description": "The request or document is invalid."},
	401: {"model": ErrorResponse, "description": "Authentication is required or invalid."},
	403: {"model": ErrorResponse, "description": "The account cannot perform this operation."},
	404: {"model": ErrorResponse, "description": "The resource is absent or hidden."},
	409: {"model": ErrorResponse, "description": "The command conflicts with current state."},
	500: {"model": ErrorResponse, "description": "The request failed without exposing internals."},
	503: {"model": ErrorResponse, "description": "A required service is unavailable."},
}
