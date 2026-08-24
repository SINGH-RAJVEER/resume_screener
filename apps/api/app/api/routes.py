import csv
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import StringIO
from pathlib import Path
from secrets import choice, token_urlsafe
from string import ascii_uppercase, digits
from typing import cast

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import AuthResult, AuthService, CredentialValidationError, InvalidCredentialsError
from ..core.http import APIError
from ..documents.ingestion import (
    DocumentValidationError,
    inspect_resume_zip,
    media_type_for_name,
    validate_resume,
)
from ..documents.storage import LocalObjectStorage
from ..persistence.models import (
    CandidateRecord,
    Evaluation,
    IndependentEvaluation,
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
    User,
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
    account_type: str
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


class OrganizationMemberRequest(RequestModel):
    email: str
    role: str


class JobRequest(RequestModel):
    organization_id: str
    title: str
    description: str


class ApplicationWindowRequest(RequestModel):
    opens_at: datetime
    closes_at: datetime

    @field_validator("opens_at", "closes_at", mode="before")
    @classmethod
    def _parse_timestamp(cls, value: object) -> object:
        # Strict pydantic rejects ISO strings during JSON body validation, so
        # parse them here; FastAPI hands the model already-decoded JSON values.
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError as error:
                raise ValueError("timestamp must be an ISO 8601 datetime") from error
        return value


class RequirementRequest(RequestModel):
    stable_id: str
    normalized_text: str
    kind: str
    weight: int


class RequirementConfirmationRequest(RequestModel):
    requirements: list[RequirementRequest]


class InvitationRequest(RequestModel):
    expires_in_hours: int = 168


class InvitationPasscodeRequest(RequestModel):
    passcode: str


router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/auth/sign-up/email", response_model=AuthResponse, status_code=201)
async def sign_up(input_data: SignUpRequest, request: Request) -> AuthResponse:
    return await register_account(input_data, request, "candidate")


@router.post("/api/employer/auth/sign-up/email", response_model=AuthResponse, status_code=201)
async def sign_up_employer(input_data: SignUpRequest, request: Request) -> AuthResponse:
    return await register_account(input_data, request, "employer")


async def register_account(
    input_data: SignUpRequest, request: Request, account_type: str
) -> AuthResponse:
    try:
        result = await auth_service(request).register(
            input_data.name,
            input_data.email,
            input_data.password,
            account_type,
        )
    except CredentialValidationError as error:
        raise APIError(400, "INVALID_CREDENTIALS", str(error)) from error
    except EmailAlreadyUsedError:
        raise APIError(409, "EMAIL_ALREADY_EXISTS", "Email is already registered") from None
    return auth_response(result)


@router.post("/api/auth/sign-in/email", response_model=AuthResponse)
async def sign_in(input_data: SignInRequest, request: Request) -> AuthResponse:
    return await sign_in_account(input_data, request, "candidate")


@router.post("/api/employer/auth/sign-in/email", response_model=AuthResponse)
async def sign_in_employer(input_data: SignInRequest, request: Request) -> AuthResponse:
    return await sign_in_account(input_data, request, "employer")


async def sign_in_account(
    input_data: SignInRequest, request: Request, account_type: str
) -> AuthResponse:
    try:
        result = await auth_service(request).sign_in(
            input_data.email, input_data.password, account_type
        )
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
        # Models declare no relationships, so flush parents before children to
        # guarantee insert order satisfies foreign keys.
        session.add(organization)
        await session.flush()
        session.add(member)
    return {"id": organization.id, "name": organization.name, "role": "owner"}


@router.get("/api/organizations/{organization_id}/members")
async def list_organization_members(organization_id: str, request: Request) -> list[dict[str, str]]:
    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions()() as session:
        await require_membership(session, organization_id, user.id)
        rows = await session.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(User.name, User.email)
        )
    return [
        {
            "userId": member.user_id,
            "name": member_user.name,
            "email": member_user.email,
            "role": member.role,
        }
        for member, member_user in rows
    ]


@router.post("/api/organizations/{organization_id}/members", status_code=201)
async def add_organization_member(
    organization_id: str, input_data: OrganizationMemberRequest, request: Request
) -> dict[str, str]:
    if input_data.role not in {"recruiter", "viewer"}:
        raise APIError(400, "INVALID_REQUEST", "Member role must be recruiter or viewer")
    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions().begin() as session:
        await require_owner(session, organization_id, user.id)
        member_user = (
            await session.execute(
                select(User).where(User.email == input_data.email.strip().lower())
            )
        ).scalar_one_or_none()
        if member_user is None or member_user.account_type != "employer":
            raise APIError(404, "NOT_FOUND", "Employer user not found")
        existing = (
            await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.user_id == member_user.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise APIError(409, "MEMBER_EXISTS", "User is already a member")
        member = OrganizationMember(
            id=new_id(),
            organization_id=organization_id,
            user_id=member_user.id,
            role=input_data.role,
        )
        session.add(member)
    return {"userId": member_user.id, "role": member.role}


@router.delete("/api/organizations/{organization_id}/members/{member_user_id}", status_code=204)
async def remove_organization_member(
    organization_id: str, member_user_id: str, request: Request
) -> None:
    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions().begin() as session:
        await require_owner(session, organization_id, user.id)
        member = (
            await session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.user_id == member_user_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise APIError(404, "NOT_FOUND", "Organization member not found")
        if member.role == "owner":
            raise APIError(409, "OWNER_REQUIRED", "Organization owner cannot be removed")
        await session.delete(member)


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


@router.post("/api/jobs", status_code=202)
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
        draft_requirements=None,
        schema_version="2",
    )
    processing_job = ProcessingJob(
        id=new_id(),
        type="job_description_processing",
        status="ready",
        payload_reference=version.id,
        idempotency_key=version.id,
        maximum_attempts=3,
    )
    async with store.sessions().begin() as session:
        await require_write_membership(session, input_data.organization_id, user.id)
        session.add(job)
        await session.flush()
        session.add(version)
        session.add(processing_job)
    return {
        "id": job.id,
        "versionId": version.id,
        "processingJobId": processing_job.id,
    }


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
        processing = (
            await session.execute(
                select(ProcessingJob)
                .where(
                    ProcessingJob.type == "job_description_processing",
                    ProcessingJob.payload_reference == version.id,
                )
                .order_by(ProcessingJob.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        artifact = version.draft_requirements or {}
        draft_status = (
            "ready"
            if artifact
            else "failed"
            if processing is not None and processing.status == "dead"
            else "processing"
        )
        return {
            "id": job.id,
            "organizationId": job.organization_id,
            "title": job.title,
            "applicationOpensAt": job.application_opens_at.isoformat()
            if job.application_opens_at
            else None,
            "applicationClosesAt": job.application_closes_at.isoformat()
            if job.application_closes_at
            else None,
            "description": version.source_text,
            "confirmed": version.confirmed_at is not None,
            "draftStatus": draft_status,
            "draftQualityState": artifact.get("qualityState"),
            "draftWarnings": artifact.get("warnings", []),
            "draftDegraded": artifact.get("degraded", False),
            "draftRequirements": artifact.get("requirements", []),
            "requirements": [
                {
                    "id": requirement.id,
                    "stableId": requirement.stable_id,
                    "text": requirement.normalized_text,
                    "kind": requirement.kind,
                    "weight": requirement.weight,
                    "category": requirement.category,
                    "sourceModality": requirement.source_modality,
                    "assessability": requirement.assessability,
                    "predicate": requirement.predicate,
                    "sourceEvidence": requirement.source_evidence,
                }
                for requirement in requirements
            ],
        }


@router.put("/api/jobs/{job_id}/application-window")
async def set_application_window(
    job_id: str, input_data: ApplicationWindowRequest, request: Request
) -> dict[str, str]:
    if input_data.opens_at.tzinfo is None or input_data.closes_at.tzinfo is None:
        raise APIError(
            400, "INVALID_REQUEST", "Application window timestamps must include a timezone"
        )
    if input_data.closes_at <= input_data.opens_at:
        raise APIError(400, "INVALID_REQUEST", "Application close must be after application open")
    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions().begin() as session:
        job = await session.get(Job, job_id)
        if job is None:
            raise APIError(404, "NOT_FOUND", "Job not found")
        await require_write_membership(session, job.organization_id, user.id)
        job.application_opens_at = input_data.opens_at
        job.application_closes_at = input_data.closes_at
    return {
        "opensAt": input_data.opens_at.isoformat(),
        "closesAt": input_data.closes_at.isoformat(),
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
        artifact = previous_version.draft_requirements or {}
        draft_by_id = requirement_drafts_by_id(artifact.get("requirements"))
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
        await session.flush()
        for requirement in input_data.requirements:
            draft: dict[str, object] = draft_by_id.get(requirement.stable_id, {})
            source_text = str(draft.get("normalizedText", "")).strip()
            metadata = draft if source_text == requirement.normalized_text.strip() else {}
            assessability = str(metadata.get("assessability", "resume_evidence"))
            if assessability != "resume_evidence" and requirement.kind != "ignored":
                raise APIError(
                    400,
                    "INVALID_REQUEST",
                    "Only resume-evidence requirements can enter automated scoring",
                )
            session.add(
                JobRequirement(
                    id=new_id(),
                    job_version_id=version.id,
                    stable_id=requirement.stable_id,
                    kind=requirement.kind,
                    weight=requirement.weight,
                    normalized_text=requirement.normalized_text,
                    category=str(metadata.get("category", "other")),
                    source_modality=str(metadata.get("sourceModality", "unclear")),
                    assessability=assessability,
                    predicate=cast(
                        dict[str, object],
                        metadata.get("predicate")
                        or {
                            "operator": "all_of",
                            "criteria": [
                                {
                                    "type": "other",
                                    "canonicalName": None,
                                    "minimumMonths": None,
                                    "minimumLevel": None,
                                    "subjects": [],
                                }
                            ],
                        },
                    ),
                    aliases=[],
                    source_evidence=cast(
                        list[dict[str, object]],
                        metadata.get("evidence") or [],
                    ),
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
        if not application_is_open(job):
            raise APIError(409, "APPLICATIONS_CLOSED", "Job applications are not open")
        passcode = "".join(choice(ascii_uppercase + digits) for _ in range(8))
        invitation = Invitation(
            id=new_id(),
            job_id=job.id,
            creator_user_id=user.id,
            token_hash=sha256(token.encode()).hexdigest(),
            passcode_hash=sha256(passcode.encode()).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(hours=input_data.expires_in_hours),
        )
        session.add(invitation)
    return {
        "id": invitation.id,
        "token": token,
        "passcode": passcode,
        "expiresAt": invitation.expires_at.isoformat(),
    }


@router.post("/api/invitations/{token}/redeem")
async def redeem_invitation(token: str, request: Request) -> dict[str, str]:
    user = await require_candidate(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions().begin() as session:
        invitation = (
            await session.execute(
                select(Invitation).where(
                    Invitation.token_hash == sha256(token.encode()).hexdigest()
                )
            )
        ).scalar_one_or_none()
        job = await session.get(Job, invitation.job_id) if invitation else None
        if (
            invitation is None
            or job is None
            or not application_is_open(job)
            or invitation.revoked_at is not None
            or invitation.expires_at <= datetime.now(UTC)
            or invitation.resume_submission_id is not None
        ):
            raise APIError(404, "NOT_FOUND", "Invitation is unavailable")
        if invitation.redeeming_user_id not in {None, user.id}:
            raise APIError(409, "INVITATION_REDEEMED", "Invitation was redeemed by another user")
        invitation.redeeming_user_id = user.id
        return {"jobId": invitation.job_id, "invitationId": invitation.id}


@router.post("/api/invitations/redeem")
async def redeem_invitation_passcode(
    input_data: InvitationPasscodeRequest, request: Request
) -> dict[str, str]:
    user = await require_candidate(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions().begin() as session:
        invitation = (
            await session.execute(
                select(Invitation).where(
                    Invitation.passcode_hash
                    == sha256(input_data.passcode.strip().upper().encode()).hexdigest()
                )
            )
        ).scalar_one_or_none()
        job = await session.get(Job, invitation.job_id) if invitation else None
        if (
            invitation is None
            or job is None
            or not application_is_open(job)
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
            if user.account_type != "candidate":
                raise APIError(403, "FORBIDDEN", "Candidate account required")
            invitation = (
                await session.execute(
                    select(Invitation).where(
                        Invitation.token_hash == sha256(invitation_token.encode()).hexdigest()
                    )
                )
            ).scalar_one_or_none()
            if invitation is None:
                invitation = (
                    await session.execute(
                        select(Invitation).where(
                            Invitation.passcode_hash
                            == sha256(invitation_token.strip().upper().encode()).hexdigest()
                        )
                    )
                ).scalar_one_or_none()
            if not application_is_open(job):
                raise APIError(409, "APPLICATIONS_CLOSED", "Job applications are not open")
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
        await add_resume_chain(
            session, candidate, document, version, submission, processing, evaluation
        )
        if invitation is not None:
            # Set after the chain flush so the update cannot be emitted before
            # the referenced submission row exists.
            invitation.resume_submission_id = submission.id
        LocalObjectStorage(Path(request.app.state.settings.storage_root)).put(
            document.storage_key, content
        )
    return {
        "processingJobId": processing.id,
        "submissionId": submission.id,
        "evaluationId": evaluation.id,
    }


@router.post("/api/jobs/{job_id}/resume-batches", status_code=202)
async def upload_resume_batch(
    job_id: str, request: Request, archive: UploadFile = File()
) -> dict[str, object]:
    """Queue each valid ZIP entry independently, reporting unsafe entries without storing them."""
    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    if archive.content_type not in {"application/zip", "application/x-zip-compressed"}:
        raise APIError(400, "INVALID_DOCUMENT", "Resume batch must be a ZIP file")
    try:
        entries = inspect_resume_zip(await archive.read())
    except DocumentValidationError as error:
        raise APIError(400, "INVALID_DOCUMENT", str(error)) from error
    accepted: list[dict[str, str]] = []
    rejected = [
        {"name": entry.name, "reason": entry.reason}
        for entry in entries
        if entry.reason is not None
    ]
    async with store.sessions().begin() as session:
        job = await session.get(Job, job_id)
        if job is None:
            raise APIError(404, "NOT_FOUND", "Job not found")
        await require_write_membership(session, job.organization_id, user.id)
        job_version = await latest_job_version(session, job.id)
        if job_version.confirmed_at is None:
            raise APIError(409, "REQUIREMENTS_NOT_CONFIRMED", "Job requirements must be confirmed")
        storage = LocalObjectStorage(Path(request.app.state.settings.storage_root))
        for entry in entries:
            if entry.content is None:
                continue
            validated = validate_resume(entry.content, media_type_for_name(entry.name), entry.name)
            candidate = CandidateRecord(id=new_id(), organization_id=job.organization_id)
            document = ResumeDocument(
                id=new_id(),
                organization_id=job.organization_id,
                candidate_record_id=candidate.id,
                storage_key=f"resumes/{new_id()}{validated.extension}",
                checksum=sha256(entry.content).hexdigest(),
                media_type=validated.media_type,
                size_bytes=len(entry.content),
                original_name=entry.name,
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
            await add_resume_chain(
                session, candidate, document, version, submission, processing, evaluation
            )
            storage.put(document.storage_key, entry.content)
            accepted.append(
                {
                    "name": entry.name,
                    "processingJobId": processing.id,
                    "submissionId": submission.id,
                    "evaluationId": evaluation.id,
                }
            )
    return {"accepted": accepted, "rejected": rejected}


@router.post("/api/independent-evaluations", status_code=202)
async def create_independent_evaluation(
    request: Request,
    file: UploadFile = File(),
    job_description: str = Form(""),
) -> dict[str, str]:
    user = await require_candidate(request)
    store = require_sqlalchemy_store(request)
    content = await file.read()
    try:
        validated = validate_resume(content, file.content_type, file.filename)
    except DocumentValidationError as error:
        raise APIError(400, "INVALID_DOCUMENT", str(error)) from error
    job_text = job_description.strip()
    if len(job_text) > 100_000:
        raise APIError(400, "INVALID_REQUEST", "Job description must be at most 100,000 characters")
    evaluation = IndependentEvaluation(
        id=new_id(),
        user_id=user.id,
        storage_key=f"independent-resumes/{new_id()}{validated.extension}",
        original_name=file.filename or "resume",
        media_type=validated.media_type,
        job_description=job_text or None,
    )
    processing = ProcessingJob(
        id=new_id(),
        type="independent_evaluation_processing",
        payload_reference=evaluation.id,
        idempotency_key=new_id(),
    )
    async with store.sessions().begin() as session:
        session.add_all([evaluation, processing])
        LocalObjectStorage(Path(request.app.state.settings.storage_root)).put(
            evaluation.storage_key, content
        )
    return {"id": evaluation.id, "processingJobId": processing.id}


@router.get("/api/independent-evaluations")
async def list_independent_evaluations(request: Request) -> list[dict[str, object]]:
    user = await require_candidate(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions()() as session:
        rows = await session.execute(
            select(IndependentEvaluation)
            .where(IndependentEvaluation.user_id == user.id)
            .order_by(IndependentEvaluation.created_at.desc())
        )
    return [independent_evaluation_summary(evaluation) for evaluation in rows.scalars()]


@router.get("/api/independent-evaluations/{evaluation_id}")
async def independent_evaluation_detail(
	evaluation_id: str, request: Request
) -> dict[str, object]:
	user = await require_candidate(request)
	store = require_sqlalchemy_store(request)
	async with store.sessions()() as session:
		evaluation = await owned_independent_evaluation(session, evaluation_id, user.id)
		return {
			**independent_evaluation_summary(evaluation),
			"jobDescriptionProvided": evaluation.job_description is not None,
			"suggestions": evaluation.suggestions or [],
			"facts": evaluation.normalized_facts or {},
			"hasImprovedResume": bool(evaluation.improved_resume_key),
		}


@router.get("/api/independent-evaluations/{evaluation_id}/improved-resume")
async def download_improved_resume(evaluation_id: str, request: Request) -> Response:
	user = await require_candidate(request)
	store = require_sqlalchemy_store(request)
	async with store.sessions().begin() as session:
		evaluation = await owned_independent_evaluation(session, evaluation_id, user.id)
	if not evaluation.improved_resume_key or not evaluation.improved_resume_unlocked_at:
		raise APIError(404, "NOT_FOUND", "Corrected resume is not available")
	content = LocalObjectStorage(Path(request.app.state.settings.storage_root)).get(
		evaluation.improved_resume_key
	)
	return Response(
		content=content,
		media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		headers={"Content-Disposition": 'attachment; filename="corrected-resume.docx"'},
	)


@router.delete("/api/independent-evaluations/{evaluation_id}", status_code=204)
async def delete_independent_evaluation(evaluation_id: str, request: Request) -> None:
    user = await require_candidate(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions().begin() as session:
        evaluation = await owned_independent_evaluation(session, evaluation_id, user.id)
        LocalObjectStorage(Path(request.app.state.settings.storage_root)).delete(evaluation.storage_key)
        await session.delete(evaluation)


@router.get("/api/processing-jobs/{processing_job_id}")
async def processing_job_status(processing_job_id: str, request: Request) -> dict[str, object]:
    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions()() as session:
        processing = await session.get(ProcessingJob, processing_job_id)
        if processing is None:
            raise APIError(404, "NOT_FOUND", "Processing job not found")
        independent_evaluation = (
            await session.execute(
                select(IndependentEvaluation).where(
                    IndependentEvaluation.id == processing.payload_reference
                )
            )
        ).scalar_one_or_none()
        if independent_evaluation is not None:
            if independent_evaluation.user_id != user.id:
                raise APIError(404, "NOT_FOUND", "Processing job not found")
            return {
                "id": processing.id,
                "status": processing.status,
                "safeError": processing.safe_error,
            }
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
async def list_evaluations(
    job_id: str,
    request: Request,
    eligibility: list[str] | None = Query(default=None),
    minimum_score: int | None = Query(default=None, ge=0, le=100),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    user = await require_user(request)
    store = require_sqlalchemy_store(request)
    async with store.sessions()() as session:
        job = await session.get(Job, job_id)
        if job is None:
            raise APIError(404, "NOT_FOUND", "Job not found")
        await require_membership(session, job.organization_id, user.id)
        statement = (
            select(Evaluation, CandidateRecord)
            .join(ResumeSubmission, ResumeSubmission.id == Evaluation.resume_submission_id)
            .join(CandidateRecord, CandidateRecord.id == ResumeSubmission.candidate_record_id)
            .where(ResumeSubmission.job_id == job.id)
            .order_by(Evaluation.score.desc().nullslast(), Evaluation.created_at.desc())
        )
        if eligibility:
            statement = statement.where(Evaluation.eligibility.in_(eligibility))
        if minimum_score is not None:
            statement = statement.where(Evaluation.score >= minimum_score)
        rows = await session.execute(statement.limit(limit))
        result: list[dict[str, object]] = []
        for evaluation, candidate in rows:
            assessments = (
                await session.execute(
                    select(RequirementAssessment, JobRequirement)
                    .join(JobRequirement)
                    .where(RequirementAssessment.evaluation_id == evaluation.id)
                )
            ).all()
            block_texts = await resume_block_texts(session, str(evaluation.resume_version_id))
            result.append(
                {
                    "id": evaluation.id,
                    "candidateName": candidate.full_name,
                    "candidateEmail": candidate.email,
                    "candidateLocation": candidate.location,
                    "status": evaluation.status,
                    "score": evaluation.score,
                    "coverage": evaluation.evidence_coverage,
                    "eligibility": evaluation.eligibility,
                    "assessments": [
                        assessment_payload(
                            assessment, requirement, block_texts
                        )
                        for assessment, requirement in assessments
                    ],
                }
            )
        return result


async def resume_block_texts(
    session: AsyncSession, version_id: str
) -> dict[str, str]:
    version = await session.get(ResumeVersion, version_id)
    extraction: dict[str, object] = dict(version.extraction_blocks or {}) if version else {}
    raw_blocks = extraction.get("blocks")
    blocks = cast(list[object], raw_blocks) if isinstance(raw_blocks, list) else None
    texts: dict[str, str] = {}
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        entry = cast(dict[str, object], block)
        block_id = entry.get("id")
        if block_id:
            texts[str(block_id)] = str(entry.get("text", ""))
    return texts


def assessment_payload(
    assessment: RequirementAssessment,
    requirement: JobRequirement,
    block_texts: dict[str, str],
) -> dict[str, object]:
    semantic = assessment.semantic_evidence
    if isinstance(semantic, dict):
        matches = semantic.get("matches")
        if isinstance(matches, list):
            for entry in cast(list[object], matches):
                if not isinstance(entry, dict):
                    continue
                match: dict[str, object] = dict(cast(dict[str, object], entry))
                match["text"] = block_texts.get(str(match.get("blockId")), "")
    return {
        "requirement": requirement.normalized_text,
        "outcome": assessment.outcome,
        "reasoning": assessment.reasoning,
        "evidence": assessment.evidence,
        "semanticEvidence": semantic,
    }


@router.get("/api/jobs/{job_id}/evaluations.csv")
async def export_evaluations_csv(job_id: str, request: Request) -> Response:
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
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["candidate_name", "status", "score", "eligibility", "evidence_coverage"])
        for evaluation, candidate in rows:
            writer.writerow(
                [
                    candidate.full_name or "",
                    evaluation.status,
                    evaluation.score if evaluation.score is not None else "",
                    evaluation.eligibility,
                    (
                        evaluation.evidence_coverage
                        if evaluation.evidence_coverage is not None
                        else ""
                    ),
                ]
            )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{job_id}-evaluations.csv"'},
    )


async def require_user(request: Request) -> UserRecord:
    user = await authenticated_user(request)
    if user is None:
        raise APIError(401, "UNAUTHORIZED", "Unauthorized")
    return user


async def require_candidate(request: Request) -> UserRecord:
    user = await require_user(request)
    if user.account_type != "candidate":
        raise APIError(403, "FORBIDDEN", "Candidate account required")
    return user


def application_is_open(job: Job) -> bool:
    now = datetime.now(UTC)
    return (
        job.application_opens_at is not None
        and job.application_closes_at is not None
        and job.application_opens_at <= now < job.application_closes_at
    )


def independent_evaluation_summary(evaluation: IndependentEvaluation) -> dict[str, object]:
    return {
        "id": evaluation.id,
        "originalName": evaluation.original_name,
        "status": evaluation.status,
        "score": evaluation.score,
        "safeError": evaluation.safe_error,
        "createdAt": evaluation.created_at.isoformat(),
        "completedAt": evaluation.completed_at.isoformat() if evaluation.completed_at else None,
    }


async def owned_independent_evaluation(
    session: AsyncSession, evaluation_id: str, user_id: str
) -> IndependentEvaluation:
    evaluation = await session.get(IndependentEvaluation, evaluation_id)
    if evaluation is None or evaluation.user_id != user_id:
        raise APIError(404, "NOT_FOUND", "Evaluation not found")
    return evaluation


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


async def add_resume_chain(
    session: AsyncSession,
    candidate: CandidateRecord,
    document: ResumeDocument,
    version: ResumeVersion,
    submission: ResumeSubmission,
    processing: ProcessingJob,
    evaluation: Evaluation,
) -> None:
    # Models declare no relationships, so flush each parent before its
    # dependent rows to guarantee insert order satisfies foreign keys.
    session.add(candidate)
    await session.flush()
    session.add(document)
    await session.flush()
    session.add(version)
    await session.flush()
    session.add(submission)
    await session.flush()
    session.add(processing)
    session.add(evaluation)


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


async def require_owner(session: AsyncSession, organization_id: str, user_id: str) -> None:
    result = await session.execute(
        select(OrganizationMember.role).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() != "owner":
        raise APIError(404, "NOT_FOUND", "Organization not found")


def new_id() -> str:
    return token_urlsafe(18)


def requirement_drafts_by_id(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, list):
        return {}
    drafts: dict[str, dict[str, object]] = {}
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            continue
        draft = cast(dict[str, object], item)
        stable_id = draft.get("stableId")
        if isinstance(stable_id, str) and stable_id:
            drafts[stable_id] = draft
    return drafts
