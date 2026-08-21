from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthResult, AuthService, CredentialValidationError, InvalidCredentialsError
from ..core.http import APIError
from ..documents.ingestion import DocumentValidationError, validate_resume
from ..documents.storage import LocalObjectStorage
from ..jobs.requirement_drafts import draft_requirements
from ..persistence.models import (
	CandidateRecord,
	Evaluation,
	Invitation,
	Job,
	JobRequirement,
	JobVersion,
	Organization,
	OrganizationMember,
	ProcessingJob,
	RequirementAssessment,
	ResumeDocument,
	ResumeSubmission,
	ResumeVersion,
)
from ..persistence.store import EmailAlreadyUsedError, SQLAlchemyStore, Store, UserRecord


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SignUpRequest(RequestModel):
    name: str = ""
    email: str = ""
    password: str = ""


class SignInRequest(RequestModel):
    email: str = ""
    password: str = ""


class ResponseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class UserResponse(ResponseModel):
    id: str
    name: str
    email: str
    email_verified: bool
    image: str | None
    created_at: datetime
    updated_at: datetime


class AuthResponse(ResponseModel):
    user: UserResponse
    token: str
    token_type: str = "Bearer"
    expires_at: datetime


class SessionResponse(ResponseModel):
	user: UserResponse


class OrganizationRequest(RequestModel):
	name: str


class JobRequest(RequestModel):
	organization_id: str
	title: str
	description: str


class RequirementRequest(RequestModel):
	stable_id: str
	normalized_text: str
	kind: str
	weight: int


class RequirementConfirmationRequest(RequestModel):
	requirements: list[RequirementRequest]


class InvitationRequest(RequestModel):
	expires_in_hours: int = 168


router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/auth/sign-up/email", response_model=AuthResponse, status_code=201)
async def sign_up(input_data: SignUpRequest, request: Request) -> AuthResponse:
    try:
        result = await auth_service(request).register(
            input_data.name,
            input_data.email,
            input_data.password,
        )
    except CredentialValidationError as error:
        raise APIError(400, "INVALID_CREDENTIALS", str(error)) from error
    except EmailAlreadyUsedError:
        raise APIError(409, "EMAIL_ALREADY_EXISTS", "Email is already registered") from None
    return auth_response(result)


@router.post("/api/auth/sign-in/email", response_model=AuthResponse)
async def sign_in(input_data: SignInRequest, request: Request) -> AuthResponse:
    try:
        result = await auth_service(request).sign_in(input_data.email, input_data.password)
    except InvalidCredentialsError:
        raise APIError(401, "INVALID_EMAIL_OR_PASSWORD", "Invalid email or password") from None
    return auth_response(result)


@router.post("/api/auth/sign-out")
async def sign_out() -> dict[str, bool]:
    return {"success": True}


@router.get("/api/auth/session", response_model=SessionResponse | None)
async def session(request: Request) -> SessionResponse | None:
    user = await authenticated_user(request)
    return None if user is None else SessionResponse(user=UserResponse.model_validate(user))


@router.get("/api/me", response_model=SessionResponse)
async def me(request: Request) -> SessionResponse:
    user = await authenticated_user(request)
    if user is None:
        raise APIError(401, "UNAUTHORIZED", "Unauthorized")
    return SessionResponse(user=UserResponse.model_validate(user))


def auth_service(request: Request) -> AuthService:
    settings = request.app.state.settings
    store: Store = request.app.state.store
    return AuthService(store, settings.jwt_secret, settings.jwt_ttl)


async def authenticated_user(request: Request) -> UserRecord | None:
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token:
        return None
    try:
        return await auth_service(request).authenticate(token)
    except InvalidCredentialsError:
        return None


def auth_response(result: AuthResult) -> AuthResponse:
    return AuthResponse(
        user=UserResponse.model_validate(result.user),
        token=result.token,
        expires_at=result.expires_at,
	)


@router.get("/api/organizations")
async def list_organizations(request: Request) -> list[dict[str, object]]:
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	async with store.sessions()() as session:
		rows = await session.execute(
			select(Organization, OrganizationMember.role)
			.join(OrganizationMember)
			.where(OrganizationMember.user_id == user.id)
			.order_by(Organization.created_at)
		)
	return [
		{"id": organization.id, "name": organization.name, "role": role}
		for organization, role in rows
	]


@router.post("/api/organizations", status_code=201)
async def create_organization(input_data: OrganizationRequest, request: Request) -> dict[str, str]:
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	organization = Organization(id=new_id(), name=input_data.name.strip())
	member = OrganizationMember(
		id=new_id(), organization_id=organization.id, user_id=user.id, role="owner"
	)
	async with store.sessions().begin() as session:
		session.add_all([organization, member])
	return {"id": organization.id, "name": organization.name, "role": "owner"}


@router.get("/api/organizations/{organization_id}/jobs")
async def list_jobs(organization_id: str, request: Request) -> list[dict[str, object]]:
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	async with store.sessions()() as session:
		latest_version = (
			select(func.max(JobVersion.version))
			.where(JobVersion.job_id == Job.id)
			.correlate(Job)
			.scalar_subquery()
		)
		await require_membership(session, organization_id, user.id)
		rows = await session.execute(
			select(Job, JobVersion)
			.join(
				JobVersion,
				(JobVersion.job_id == Job.id) & (JobVersion.version == latest_version),
			)
			.where(Job.organization_id == organization_id)
			.order_by(Job.created_at.desc(), JobVersion.version.desc())
		)
	return [
		{
			"id": job.id,
			"title": job.title,
			"versionId": version.id,
			"confirmed": version.confirmed_at is not None,
		}
		for job, version in rows
	]


@router.post("/api/jobs", status_code=201)
async def create_job(input_data: JobRequest, request: Request) -> dict[str, str]:
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	job = Job(
		id=new_id(), organization_id=input_data.organization_id, title=input_data.title.strip()
	)
	version = JobVersion(
		id=new_id(),
		job_id=job.id,
		version=1,
		source_text=input_data.description,
		normalized_text=input_data.description.strip(),
		source_media_type="text/plain",
		draft_requirements={"requirements": draft_requirements(input_data.description)},
	)
	async with store.sessions().begin() as session:
		await require_write_membership(session, input_data.organization_id, user.id)
		session.add_all([job, version])
	return {"id": job.id, "versionId": version.id}


@router.get("/api/jobs/{job_id}")
async def job_detail(job_id: str, request: Request) -> dict[str, object]:
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	async with store.sessions()() as session:
		job = await session.get(Job, job_id)
		if job is None:
			raise APIError(404, "NOT_FOUND", "Job not found")
		await require_write_membership(session, job.organization_id, user.id)
		version = await latest_job_version(session, job.id)
		requirements = (
			await session.execute(
				select(JobRequirement).where(JobRequirement.job_version_id == version.id)
			)
		).scalars()
		return {
			"id": job.id,
			"organizationId": job.organization_id,
			"title": job.title,
			"description": version.source_text,
			"confirmed": version.confirmed_at is not None,
			"draftRequirements": version.draft_requirements.get("requirements", [])
			if version.draft_requirements
			else [],
			"requirements": [
				{
					"id": requirement.id,
					"stableId": requirement.stable_id,
					"text": requirement.normalized_text,
					"kind": requirement.kind,
					"weight": requirement.weight,
				}
				for requirement in requirements
			],
		}


@router.post("/api/jobs/{job_id}/requirements", status_code=201)
async def confirm_requirements(
	job_id: str, input_data: RequirementConfirmationRequest, request: Request
) -> dict[str, bool]:
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	allowed_kinds = {"required", "preferred", "ignored", "hard_gate"}
	if any(requirement.kind not in allowed_kinds for requirement in input_data.requirements):
		raise APIError(400, "INVALID_REQUEST", "Invalid requirement kind")
	async with store.sessions().begin() as session:
		job = await session.get(Job, job_id)
		if job is None:
			raise APIError(404, "NOT_FOUND", "Job not found")
		await require_write_membership(session, job.organization_id, user.id)
		previous_version = await latest_job_version(session, job.id)
		version = JobVersion(
			id=new_id(),
			job_id=job.id,
			version=previous_version.version + 1,
			source_text=previous_version.source_text,
			normalized_text=previous_version.normalized_text,
			source_media_type=previous_version.source_media_type,
			draft_requirements=previous_version.draft_requirements,
			schema_version=previous_version.schema_version,
			confirmed_at=datetime.now(UTC),
		)
		session.add(version)
		for requirement in input_data.requirements:
			session.add(
				JobRequirement(
					id=new_id(), job_version_id=version.id, stable_id=requirement.stable_id,
					kind=requirement.kind, weight=requirement.weight,
					normalized_text=requirement.normalized_text, aliases=[], source_evidence=[],
				)
			)
	return {"confirmed": True}


@router.post("/api/jobs/{job_id}/invitations", status_code=201)
async def create_invitation(
	job_id: str, input_data: InvitationRequest, request: Request
) -> dict[str, str]:
	if not 1 <= input_data.expires_in_hours <= 24 * 30:
		raise APIError(
			400, "INVALID_REQUEST", "Invitation expiry must be between 1 hour and 30 days"
		)
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	token = token_urlsafe(32)
	async with store.sessions().begin() as session:
		job = await session.get(Job, job_id)
		if job is None:
			raise APIError(404, "NOT_FOUND", "Job not found")
		await require_write_membership(session, job.organization_id, user.id)
		invitation = Invitation(
			id=new_id(),
			job_id=job.id,
			creator_user_id=user.id,
			token_hash=sha256(token.encode()).hexdigest(),
			expires_at=datetime.now(UTC) + timedelta(hours=input_data.expires_in_hours),
		)
		session.add(invitation)
	return {"id": invitation.id, "token": token, "expiresAt": invitation.expires_at.isoformat()}


@router.post("/api/invitations/{token}/redeem")
async def redeem_invitation(token: str, request: Request) -> dict[str, str]:
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	async with store.sessions().begin() as session:
		invitation = (
			await session.execute(
				select(Invitation).where(
					Invitation.token_hash == sha256(token.encode()).hexdigest()
				)
			)
		).scalar_one_or_none()
		if (
			invitation is None
			or invitation.revoked_at is not None
			or invitation.expires_at <= datetime.now(UTC)
			or invitation.resume_submission_id is not None
		):
			raise APIError(404, "NOT_FOUND", "Invitation is unavailable")
		if invitation.redeeming_user_id not in {None, user.id}:
			raise APIError(409, "INVITATION_REDEEMED", "Invitation was redeemed by another user")
		invitation.redeeming_user_id = user.id
		return {"jobId": invitation.job_id, "invitationId": invitation.id}


@router.post("/api/jobs/{job_id}/resumes", status_code=202)
async def upload_resume(
	job_id: str,
	request: Request,
	file: UploadFile = File(),
	candidate_name: str = Form(""),
	invitation_token: str = Form(""),
) -> dict[str, str]:
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	content = await file.read()
	try:
		validated = validate_resume(content, file.content_type, file.filename)
	except DocumentValidationError as error:
		raise APIError(400, "INVALID_DOCUMENT", str(error)) from error
	async with store.sessions().begin() as session:
		job = await session.get(Job, job_id)
		if job is None:
			raise APIError(404, "NOT_FOUND", "Job not found")
		invitation: Invitation | None = None
		if invitation_token:
			invitation = (
				await session.execute(
					select(Invitation).where(
						Invitation.token_hash == sha256(invitation_token.encode()).hexdigest()
					)
				)
			).scalar_one_or_none()
			if (
				invitation is None
				or invitation.job_id != job.id
				or invitation.redeeming_user_id != user.id
				or invitation.expires_at <= datetime.now(UTC)
				or invitation.revoked_at is not None
				or invitation.resume_submission_id is not None
			):
				raise APIError(404, "NOT_FOUND", "Invitation is unavailable")
		else:
			await require_write_membership(session, job.organization_id, user.id)
		job_version = await latest_job_version(session, job.id)
		if job_version.confirmed_at is None:
			raise APIError(409, "REQUIREMENTS_NOT_CONFIRMED", "Job requirements must be confirmed")
		candidate = CandidateRecord(
			id=new_id(),
			organization_id=job.organization_id,
			user_id=user.id if invitation is not None else None,
			full_name=candidate_name or None,
		)
		document = ResumeDocument(
			id=new_id(),
			organization_id=job.organization_id,
			candidate_record_id=candidate.id,
			storage_key=f"resumes/{new_id()}{validated.extension}",
			checksum=sha256(content).hexdigest(),
			media_type=validated.media_type,
			size_bytes=len(content),
			original_name=file.filename or "resume",
			retention_date=datetime.now(UTC) + timedelta(days=90),
		)
		version = ResumeVersion(
			id=new_id(),
			organization_id=job.organization_id,
			resume_document_id=document.id,
			version=1,
		)
		submission = ResumeSubmission(
			id=new_id(),
			organization_id=job.organization_id,
			job_id=job.id,
			candidate_record_id=candidate.id,
			resume_version_id=version.id,
			submitting_user_id=user.id,
		)
		processing = ProcessingJob(
			id=new_id(),
			type="resume_processing",
			payload_reference=version.id,
			idempotency_key=new_id(),
		)
		evaluation = Evaluation(
			id=new_id(),
			resume_submission_id=submission.id,
			job_version_id=job_version.id,
			resume_version_id=version.id,
		)
		if invitation is not None:
			invitation.resume_submission_id = submission.id
		session.add_all([candidate, document, version, submission, processing, evaluation])
		LocalObjectStorage(Path(request.app.state.settings.storage_root)).put(
			document.storage_key, content
		)
	return {
		"processingJobId": processing.id,
		"submissionId": submission.id,
		"evaluationId": evaluation.id,
	}


@router.get("/api/processing-jobs/{processing_job_id}")
async def processing_job_status(processing_job_id: str, request: Request) -> dict[str, object]:
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	async with store.sessions()() as session:
		processing = await session.get(ProcessingJob, processing_job_id)
		if processing is None:
			raise APIError(404, "NOT_FOUND", "Processing job not found")
		submission = (
			await session.execute(
				select(ResumeSubmission).where(
					ResumeSubmission.resume_version_id == processing.payload_reference
				)
			)
		).scalar_one_or_none()
		if submission is None:
			raise APIError(404, "NOT_FOUND", "Processing job not found")
		await require_membership(session, submission.organization_id, user.id)
		return {
			"id": processing.id,
			"status": processing.status,
			"safeError": processing.safe_error,
		}


@router.get("/api/jobs/{job_id}/evaluations")
async def list_evaluations(job_id: str, request: Request) -> list[dict[str, object]]:
	user = await require_user(request)
	store = require_sqlalchemy_store(request)
	async with store.sessions()() as session:
		job = await session.get(Job, job_id)
		if job is None:
			raise APIError(404, "NOT_FOUND", "Job not found")
		await require_membership(session, job.organization_id, user.id)
		rows = await session.execute(
			select(Evaluation, CandidateRecord)
			.join(ResumeSubmission, ResumeSubmission.id == Evaluation.resume_submission_id)
			.join(CandidateRecord, CandidateRecord.id == ResumeSubmission.candidate_record_id)
			.where(ResumeSubmission.job_id == job.id)
			.order_by(Evaluation.score.desc().nullslast(), Evaluation.created_at.desc())
		)
		result: list[dict[str, object]] = []
		for evaluation, candidate in rows:
			assessments = (
				await session.execute(
					select(RequirementAssessment, JobRequirement)
					.join(JobRequirement)
					.where(RequirementAssessment.evaluation_id == evaluation.id)
				)
			).all()
			result.append(
				{
					"id": evaluation.id,
					"candidateName": candidate.full_name,
					"status": evaluation.status,
					"score": evaluation.score,
					"coverage": evaluation.evidence_coverage,
					"eligibility": evaluation.eligibility,
					"assessments": [
						{
							"requirement": requirement.normalized_text,
							"outcome": assessment.outcome,
							"reasoning": assessment.reasoning,
							"evidence": assessment.evidence,
						}
						for assessment, requirement in assessments
					],
				}
			)
		return result


async def require_user(request: Request) -> UserRecord:
	user = await authenticated_user(request)
	if user is None:
		raise APIError(401, "UNAUTHORIZED", "Unauthorized")
	return user


async def latest_job_version(session: AsyncSession, job_id: str) -> JobVersion:
	version = (
		await session.execute(
			select(JobVersion)
			.where(JobVersion.job_id == job_id)
			.order_by(JobVersion.version.desc())
			.limit(1)
		)
	).scalar_one()
	return version


def require_sqlalchemy_store(request: Request) -> SQLAlchemyStore:
	store = request.app.state.store
	if not isinstance(store, SQLAlchemyStore):
		raise APIError(503, "SERVICE_UNAVAILABLE", "Workspace storage is unavailable")
	return store


async def require_membership(session: AsyncSession, organization_id: str, user_id: str) -> None:
	result = await session.execute(
		select(OrganizationMember).where(
			OrganizationMember.organization_id == organization_id,
			OrganizationMember.user_id == user_id,
		)
	)
	if result.scalar_one_or_none() is None:
		raise APIError(404, "NOT_FOUND", "Organization not found")


async def require_write_membership(
	session: AsyncSession, organization_id: str, user_id: str
) -> None:
	result = await session.execute(
		select(OrganizationMember.role).where(
			OrganizationMember.organization_id == organization_id,
			OrganizationMember.user_id == user_id,
		)
	)
	if result.scalar_one_or_none() not in {"owner", "recruiter"}:
		raise APIError(404, "NOT_FOUND", "Organization not found")


def new_id() -> str:
	return token_urlsafe(18)
