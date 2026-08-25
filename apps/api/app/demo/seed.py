"""Shared guided-demo world.

The seeder inserts a fixed, coherent dataset (one employer organization with
completed batch evaluations, one candidate account with private reports) so
the landing-page walkthrough can show real screens without live inference.
All identifiers are stable, which makes re-seeding idempotent, and demo rows
carry far-future retention dates so the sweep never removes them mid-tour.
"""

import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from secrets import token_urlsafe

from sqlalchemy import func, select, text

from ..billing.allowance import week_start
from ..core.config import Settings
from ..documents.storage import LocalObjectStorage
from ..domain.versions import (
    JOB_REQUIREMENTS_COMPILER_VERSION,
    JOB_REQUIREMENTS_PROMPT_VERSION,
    JOB_REQUIREMENTS_SCHEMA_VERSION,
)
from ..persistence.models import (
    Account,
    BatchEvaluation,
    BatchEvaluationSubmission,
    CandidateRecord,
    Evaluation,
    IndependentEvaluation,
    Job,
    JobRequirement,
    JobVersion,
    Organization,
    OrganizationMember,
    PointAccount,
    PointLedgerEntry,
    ProcessingJob,
    RequirementAssessment,
    ResumeDocument,
    ResumeSubmission,
    ResumeVersion,
    User,
    WeeklyFreeUse,
)
from ..persistence.store import SQLAlchemyStore

DEMO_SEED_LOCK = "skillsignal-demo-seed"
DEMO_EMPLOYER_USER_ID = "demo-user-employer-owner"
DEMO_CANDIDATE_USER_ID = "demo-user-candidate"
DEMO_ORGANIZATION_ID = "demo-organization"
DEMO_JOB_ID = "demo-job"

_DEMO_RETENTION = timedelta(days=3650)


@dataclass(frozen=True)
class Block:
    id: str
    page: int
    text: str


@dataclass(frozen=True)
class CandidateWorld:
    key: str
    name: str
    email: str
    location: str
    blocks: list[Block]
    skills: list[str]
    # Per confirmed requirement stable id, in the order REQUIREMENTS declares.
    outcomes: dict[str, tuple[str, str]]


@dataclass
class DemoWorld:
    users: list[User] = field(default_factory=list[User])
    accounts_auth: list[Account] = field(default_factory=list[Account])
    organization: Organization | None = None
    members: list[OrganizationMember] = field(default_factory=list[OrganizationMember])
    job: Job | None = None
    job_version: JobVersion | None = None
    requirements: list[JobRequirement] = field(default_factory=list[JobRequirement])
    draft_requirements: dict[str, object] = field(default_factory=lambda: {})
    candidates: list[CandidateRecord] = field(default_factory=list[CandidateRecord])
    documents: list[ResumeDocument] = field(default_factory=list[ResumeDocument])
    versions: list[ResumeVersion] = field(default_factory=list[ResumeVersion])
    submissions: list[ResumeSubmission] = field(default_factory=list[ResumeSubmission])
    processing_jobs: list[ProcessingJob] = field(default_factory=list[ProcessingJob])
    batch_evaluation: BatchEvaluation | None = None
    batch_submissions: list[BatchEvaluationSubmission] = field(
        default_factory=list[BatchEvaluationSubmission]
    )
    evaluations: list[Evaluation] = field(default_factory=list[Evaluation])
    assessments: list[RequirementAssessment] = field(default_factory=list[RequirementAssessment])
    point_accounts: list[PointAccount] = field(default_factory=list[PointAccount])
    ledger_entries: list[PointLedgerEntry] = field(default_factory=list[PointLedgerEntry])
    independent_evaluations: list[IndependentEvaluation] = field(
        default_factory=list[IndependentEvaluation]
    )
    weekly_free_use: WeeklyFreeUse | None = None
    files: dict[str, bytes] = field(default_factory=lambda: {})


@dataclass(frozen=True)
class RequirementSpec:
    stable_id: str
    kind: str
    weight: int
    normalized_text: str
    category: str
    predicate: dict[str, object]
    quote: str
    assessability: str = "resume_evidence"


REQUIREMENTS = [
    RequirementSpec(
        stable_id="req-python",
        kind="required",
        weight=2,
        normalized_text="At least five years of professional Python experience",
        category="skills",
        predicate={
            "operator": "all_of",
            "criteria": [
                {
                    "type": "skill",
                    "canonicalName": "Python",
                    "minimumMonths": 60,
                    "minimumLevel": None,
                    "subjects": [],
                }
            ],
        },
        quote="At least five years of professional Python experience",
    ),
    RequirementSpec(
        stable_id="req-kubernetes",
        kind="preferred",
        weight=1,
        normalized_text="Experience operating Kubernetes in production",
        category="skills",
        predicate={
            "operator": "all_of",
            "criteria": [
                {
                    "type": "skill",
                    "canonicalName": "Kubernetes",
                    "minimumMonths": None,
                    "minimumLevel": None,
                    "subjects": [],
                }
            ],
        },
        quote="Experience operating Kubernetes in production",
    ),
    RequirementSpec(
        stable_id="req-postgres",
        kind="required",
        weight=2,
        normalized_text="Production experience with PostgreSQL",
        category="skills",
        predicate={
            "operator": "all_of",
            "criteria": [
                {
                    "type": "skill",
                    "canonicalName": "PostgreSQL",
                    "minimumMonths": None,
                    "minimumLevel": None,
                    "subjects": [],
                }
            ],
        },
        quote="Production experience with PostgreSQL",
    ),
    RequirementSpec(
        stable_id="req-degree",
        kind="hard_gate",
        weight=1,
        normalized_text="Bachelor's degree in Computer Science or a related field",
        category="education",
        predicate={
            "operator": "all_of",
            "criteria": [
                {
                    "type": "education",
                    "canonicalName": None,
                    "minimumMonths": None,
                    "minimumLevel": "bachelor",
                    "subjects": ["Computer Science"],
                }
            ],
        },
        quote="Bachelor's degree in Computer Science or a related field",
    ),
    RequirementSpec(
        stable_id="req-rust",
        kind="ignored",
        weight=1,
        normalized_text="Rust experience is welcome but not evaluated",
        category="skills",
        assessability="recruiter_review",
        predicate={"operator": "all_of", "criteria": []},
        quote="Rust experience is welcome but not evaluated",
    ),
]

JOB_DESCRIPTION_TEXT = """Senior Platform Engineer - Northwind Robotics

We build the fleet software that keeps autonomous warehouse robots moving.
Our platform team owns ingestion, scheduling, and telemetry services that
process millions of robot events per day.

What we ask for:
- At least five years of professional Python experience.
- Experience operating Kubernetes in production.
- Production experience with PostgreSQL.
- Bachelor's degree in Computer Science or a related field.

What we value but do not require:
- Rust experience is welcome but not evaluated.
"""

CANDIDATES = [
    CandidateWorld(
        key="priya-sharma",
        name="Priya Sharma",
        email="priya.sharma@example.com",
        location="Bengaluru, IN",
        skills=["Python", "Kubernetes", "PostgreSQL", "Terraform"],
        blocks=[
            Block("p1", 1, "Priya Sharma - Platform Engineer, Bengaluru IN"),
            Block(
                "p2",
                1,
                "Skills: Python (8 years), Kubernetes, PostgreSQL, Terraform",
            ),
            Block(
                "p3",
                1,
                "Ran production Kubernetes clusters across three regions and "
                "migrated core services to PostgreSQL with zero downtime.",
            ),
            Block("p4", 1, "MSc Computer Science, IIT Delhi, 2017"),
        ],
        outcomes={
            "req-python": (
                "met",
                "Documents eight years of Python, above the five-year threshold.",
            ),
            "req-kubernetes": (
                "partial",
                "Names Kubernetes and cluster operations, but does not evidence "
                "production ownership depth.",
            ),
            "req-postgres": (
                "met",
                "Describes migrating core services to PostgreSQL in production.",
            ),
            "req-degree": (
                "met",
                "Lists an MSc in Computer Science, which satisfies the gate.",
            ),
        },
    ),
    CandidateWorld(
        key="marcus-chen",
        name="Marcus Chen",
        email="marcus.chen@example.com",
        location="Singapore",
        skills=["Python", "Docker", "PostgreSQL"],
        blocks=[
            Block("m1", 1, "Marcus Chen - Backend Engineer, Singapore"),
            Block("m2", 1, "Skills: Python (3 years), Docker, PostgreSQL"),
            Block(
                "m3",
                1,
                "Built billing services on PostgreSQL; containerized legacy "
                "jobs with Docker. BSc Information Systems, NUS, 2021.",
            ),
        ],
        outcomes={
            "req-python": (
                "partial",
                "Shows three years of Python against a five-year threshold.",
            ),
            "req-kubernetes": (
                "unknown",
                "No Kubernetes evidence appears anywhere in the resume.",
            ),
            "req-postgres": (
                "met",
                "Billing services were built directly on PostgreSQL.",
            ),
            "req-degree": (
                "met",
                "BSc in Information Systems is a related field.",
            ),
        },
    ),
    CandidateWorld(
        key="ana-reyes",
        name="Ana Reyes",
        email="ana.reyes@example.com",
        location="Madrid, ES",
        skills=["Python", "Kubernetes", "Redis"],
        blocks=[
            Block("a1", 1, "Ana Reyes - Infrastructure Engineer, Madrid ES"),
            Block("a2", 1, "Skills: Python (6 years), Kubernetes, Redis"),
            Block(
                "a3",
                1,
                "Operated Kubernetes for internal tooling and wrote Python "
                "tooling for release automation.",
            ),
        ],
        outcomes={
            "req-python": (
                "partial",
                "Six years of Python tooling is professional but narrower than "
                "platform service work.",
            ),
            "req-kubernetes": (
                "met",
                "Operated Kubernetes clusters for internal tooling.",
            ),
            "req-postgres": (
                "unknown",
                "The resume mentions Redis but no PostgreSQL evidence.",
            ),
            "req-degree": (
                "unknown",
                "No education section is present, so the gate cannot be confirmed or contradicted.",
            ),
        },
    ),
    CandidateWorld(
        key="tom-becker",
        name="Tom Becker",
        email="tom.becker@example.com",
        location="Berlin, DE",
        skills=["Python", "PostgreSQL", "Kafka"],
        blocks=[
            Block("t1", 1, "Tom Becker - Data Engineer, Berlin DE"),
            Block("t2", 1, "Skills: Python (7 years), Kafka, PostgreSQL"),
            Block(
                "t3",
                1,
                "Self-taught developer; completed an online data engineering "
                "certificate after high school.",
            ),
        ],
        outcomes={
            "req-python": ("met", "Seven documented years of Python work."),
            "req-kubernetes": (
                "unknown",
                "Kubernetes is never mentioned in the resume.",
            ),
            "req-postgres": (
                "partial",
                "PostgreSQL appears in a skills line without production context.",
            ),
            "req-degree": (
                "not_met",
                "States self-taught background with only an online certificate, "
                "which contradicts the degree requirement.",
            ),
        },
    ),
    CandidateWorld(
        key="omar-haddad",
        name="Omar Haddad",
        email="omar.haddad@example.com",
        location="Toronto, CA",
        skills=["Python", "Kubernetes", "PostgreSQL", "Redis"],
        blocks=[
            Block("o1", 1, "Omar Haddad - Platform Engineer, Toronto CA"),
            Block("o2", 1, "Skills: Python (6 years), Kubernetes, PostgreSQL, Redis"),
            Block(
                "o3",
                1,
                "Deployed Kubernetes workloads for customer-facing services and "
                "tuned PostgreSQL read replicas under load.",
            ),
            Block("o4", 1, "BSc Computer Engineering, McGill, 2018"),
        ],
        outcomes={
            "req-python": ("met", "Six documented years of professional Python."),
            "req-kubernetes": (
                "partial",
                "Customer-facing Kubernetes deployments are evidenced, but "
                "cluster ownership depth is unclear.",
            ),
            "req-postgres": (
                "partial",
                "Tuned read replicas, which touches PostgreSQL operations "
                "without proving full production ownership.",
            ),
            "req-degree": ("met", "Holds a BSc in Computer Engineering."),
        },
    ),
    CandidateWorld(
        key="lena-kowalski",
        name="Lena Kowalski",
        email="lena.kowalski@example.com",
        location="Warsaw, PL",
        skills=["Python", "Kubernetes", "PostgreSQL", "Grafana"],
        blocks=[
            Block("l1", 1, "Lena Kowalski - SRE, Warsaw PL"),
            Block("l2", 1, "Skills: Python (4 years), Kubernetes, PostgreSQL, Grafana"),
            Block(
                "l3",
                1,
                "Kept staging Kubernetes healthy and supported on-call for "
                "PostgreSQL replicas. BSc Computer Science, UW, 2020.",
            ),
        ],
        outcomes={
            "req-python": (
                "partial",
                "Four years of Python sits below the five-year bar.",
            ),
            "req-kubernetes": (
                "partial",
                "Staging-only Kubernetes stewardship, not production ownership.",
            ),
            "req-postgres": (
                "met",
                "On-call support for production PostgreSQL replicas.",
            ),
            "req-degree": ("met", "Holds a BSc in Computer Science."),
        },
    ),
]


def score_from_outcomes(outcomes: dict[str, str]) -> int | None:
    weighted = _scored_requirements(outcomes)
    confident = [(w, o) for w, o in weighted if o != "unknown"]
    if not confident:
        return None
    total = sum(w for w, _o in confident)
    earned = sum(w * {"met": 1.0, "partial": 0.5, "not_met": 0.0}[o] for w, o in confident)
    return round(100 * earned / total)


def coverage_from_outcomes(outcomes: dict[str, str]) -> int:
    weighted = _scored_requirements(outcomes)
    total = sum(w for w, _o in weighted)
    confident = sum(w for w, o in weighted if o != "unknown")
    return round(100 * confident / total)


def _scored_requirements(outcomes: dict[str, str]) -> list[tuple[int, str]]:
    return [
        (requirement.weight, outcomes[requirement.stable_id])
        for requirement in REQUIREMENTS
        if requirement.kind not in {"hard_gate", "ignored"}
    ]


def eligibility_for_candidate(spec: CandidateWorld) -> str:
    gate_outcomes = [
        outcome
        for stable_id, (outcome, _reason) in spec.outcomes.items()
        if _requirement_kind(stable_id) == "hard_gate"
    ]
    if any(outcome == "not_met" for outcome in gate_outcomes):
        return "not_eligible"
    if any(outcome != "met" for outcome in gate_outcomes):
        return "needs_review"
    return "eligible"


def _requirement_kind(stable_id: str) -> str:
    return next(r.kind for r in REQUIREMENTS if r.stable_id == stable_id)


# Which resume block backs each requirement's evidence, by stable id.
EVIDENCE_BLOCK_OFFSETS = {
    "req-python": 1,
    "req-kubernetes": 2,
    "req-postgres": 2,
}


def _evidence_block(spec: CandidateWorld, stable_id: str) -> Block:
    offset = EVIDENCE_BLOCK_OFFSETS.get(stable_id, len(spec.blocks) - 1)
    offset = max(0, min(offset, len(spec.blocks) - 1))
    return spec.blocks[offset]


def _resume_text(blocks: list[Block]) -> str:
    return "\n\n".join(block.text for block in blocks)


def _minimal_docx(paragraphs: Sequence[str]) -> bytes:
    document = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{line}</w:t></w:r></w:p>' for line in paragraphs
    )
    buffer = BytesIO()
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{document}</w:body></w:document>",
        )
    return buffer.getvalue()


def build_demo_world(now: datetime) -> DemoWorld:
    world = DemoWorld()
    base = now - timedelta(days=3)

    owner = User(
        id=DEMO_EMPLOYER_USER_ID,
        name="Demo Owner",
        email="owner@demo.example",
        account_type="employer",
        is_demo=True,
        created_at=base,
        updated_at=base,
    )
    recruiter = User(
        id="demo-user-employer-recruiter",
        name="Priya Recruiter",
        email="recruiter@demo.example",
        account_type="employer",
        is_demo=True,
        created_at=base,
        updated_at=base,
    )
    candidate = User(
        id=DEMO_CANDIDATE_USER_ID,
        name="Demo Candidate",
        email="candidate@demo.example",
        account_type="candidate",
        is_demo=True,
        created_at=base,
        updated_at=base,
    )
    world.users = [owner, recruiter, candidate]
    password_hash = "!"  # No credential sign-in: bcrypt of an unguessable secret.
    world.accounts_auth = [
        Account(
            id=f"demo-account-{user.id}",
            account_id=user.email,
            provider_id="credential",
            user_id=user.id,
            password=password_hash,
            created_at=base,
            updated_at=base,
        )
        for user in world.users
    ]

    world.organization = Organization(
        id=DEMO_ORGANIZATION_ID,
        name="Northwind Robotics",
        retention_days=90,
        created_at=base,
        updated_at=base,
    )
    world.members = [
        OrganizationMember(
            id="demo-member-owner",
            organization_id=world.organization.id,
            user_id=owner.id,
            role="owner",
            created_at=base,
        ),
        OrganizationMember(
            id="demo-member-recruiter",
            organization_id=world.organization.id,
            user_id=recruiter.id,
            role="recruiter",
            created_at=base,
        ),
    ]

    job_created = base + timedelta(hours=1)
    world.job = Job(
        id=DEMO_JOB_ID,
        organization_id=world.organization.id,
        title="Senior Platform Engineer",
        application_opens_at=job_created,
        application_closes_at=now + timedelta(days=30),
        created_at=job_created,
        updated_at=job_created,
    )

    drafts: list[dict[str, object]] = []
    for requirement in REQUIREMENTS:
        assessability = requirement.assessability
        kind = "ignored" if assessability != "resume_evidence" else requirement.kind
        suggested_kind = kind if kind != "hard_gate" else "required"
        drafts.append(
            {
                "stableId": requirement.stable_id,
                "normalizedText": requirement.normalized_text,
                "category": requirement.category,
                "sourceModality": "text",
                "assessability": assessability,
                "suggestedKind": suggested_kind,
                "suggestedWeight": requirement.weight,
                "confidence": 0.9,
                "predicate": requirement.predicate,
                "evidence": [
                    {
                        "blockId": "jd-requirements",
                        "quote": requirement.quote,
                    }
                ],
            }
        )
    world.draft_requirements = {
        "qualityState": "ready",
        "warnings": [],
        "degraded": False,
        "requirements": drafts,
    }

    version_confirmed = job_created + timedelta(minutes=10)
    world.job_version = JobVersion(
        id="demo-job-version-1",
        job_id=world.job.id,
        version=1,
        source_text=JOB_DESCRIPTION_TEXT,
        normalized_text=JOB_DESCRIPTION_TEXT.strip(),
        source_media_type="text/plain",
        source_storage_key=None,
        draft_requirements=world.draft_requirements,
        schema_version=JOB_REQUIREMENTS_SCHEMA_VERSION,
        prompt_version=JOB_REQUIREMENTS_PROMPT_VERSION,
        compiler_version=JOB_REQUIREMENTS_COMPILER_VERSION,
        confirmed_at=version_confirmed,
        created_at=job_created,
    )
    world.requirements = [
        JobRequirement(
            id=f"dj-{requirement.stable_id}",
            job_version_id=world.job_version.id,
            stable_id=requirement.stable_id,
            kind=requirement.kind,
            weight=requirement.weight,
            normalized_text=requirement.normalized_text,
            category=requirement.category,
            source_modality="text",
            assessability=requirement.assessability,
            predicate=requirement.predicate,
            aliases=[],
            source_evidence=[{"blockId": "jd-requirements", "quote": requirement.quote}],
            confirmed_at=version_confirmed,
        )
        for requirement in REQUIREMENTS
    ]

    world.batch_evaluation = BatchEvaluation(
        id="demo-batch-evaluation",
        organization_id=world.organization.id,
        job_id=world.job.id,
        job_version_id=world.job_version.id,
        created_by_user_id=owner.id,
        requirement_schema_version=JOB_REQUIREMENTS_SCHEMA_VERSION,
        model_configuration={},
        created_at=version_confirmed + timedelta(minutes=5),
    )

    for offset, spec in enumerate(CANDIDATES):
        moment = version_confirmed + timedelta(minutes=15 + 5 * offset)
        record = CandidateRecord(
            id=f"demo-candidate-{spec.key}",
            organization_id=world.organization.id,
            full_name=spec.name,
            email=spec.email,
            location=spec.location,
            created_at=moment,
            updated_at=moment,
        )
        document = ResumeDocument(
            id=f"demo-document-{spec.key}",
            organization_id=world.organization.id,
            candidate_record_id=record.id,
            storage_key=f"demo/resumes/{spec.key}.txt",
            checksum=token_urlsafe(12),
            media_type="text/plain",
            size_bytes=len(_resume_text(spec.blocks).encode()),
            original_name=f"{spec.key}-resume.txt",
            retention_date=now + _DEMO_RETENTION,
            created_at=moment,
        )
        version = ResumeVersion(
            id=f"demo-resume-version-{spec.key}",
            organization_id=world.organization.id,
            resume_document_id=document.id,
            version=1,
            extraction_blocks={
                "blocks": [
                    {"id": block.id, "page": block.page, "text": block.text}
                    for block in spec.blocks
                ],
                "metadata": {
                    "mediaType": "text/plain",
                    "pageCount": 1,
                    "blockCount": len(spec.blocks),
                    "characterCount": len(_resume_text(spec.blocks)),
                },
            },
            structured_facts={"skills": [{"canonicalName": skill} for skill in spec.skills]},
            normalized_facts={
                "skills": [{"canonicalName": skill} for skill in spec.skills],
                "warnings": [],
            },
            quality_state="ready",
            parser_version="demo",
            schema_version="demo",
            created_at=moment + timedelta(minutes=2),
        )
        submission = ResumeSubmission(
            id=f"demo-submission-{spec.key}",
            organization_id=world.organization.id,
            job_id=world.job.id,
            candidate_record_id=record.id,
            resume_version_id=version.id,
            created_at=moment + timedelta(minutes=4),
        )
        processing = ProcessingJob(
            id=f"demo-processing-{spec.key}",
            type="resume_processing",
            status="complete",
            payload_reference=version.id,
            idempotency_key=f"demo:{spec.key}",
            created_at=moment + timedelta(minutes=4),
            updated_at=moment + timedelta(minutes=9),
        )
        batch_submission = BatchEvaluationSubmission(
            organization_id=world.organization.id,
            job_id=world.job.id,
            batch_evaluation_id=world.batch_evaluation.id,
            resume_submission_id=submission.id,
            created_at=moment + timedelta(minutes=5),
        )
        if offset == len(CANDIDATES) - 1:
            # One submission stays mid-flight so progress states are visible.
            evaluation = Evaluation(
                id=f"demo-evaluation-{spec.key}",
                batch_evaluation_id=world.batch_evaluation.id,
                resume_submission_id=submission.id,
                job_version_id=world.job_version.id,
                resume_version_id=version.id,
                status="processing",
                score=None,
                evidence_coverage=None,
                eligibility="pending",
                quality_state="pending",
                created_at=moment + timedelta(minutes=5),
            )
        else:
            outcomes = {
                stable_id: outcome for stable_id, (outcome, _reason) in spec.outcomes.items()
            }
            evaluation = Evaluation(
                id=f"demo-evaluation-{spec.key}",
                batch_evaluation_id=world.batch_evaluation.id,
                resume_submission_id=submission.id,
                job_version_id=world.job_version.id,
                resume_version_id=version.id,
                status="complete",
                score=score_from_outcomes(outcomes),
                evidence_coverage=coverage_from_outcomes(outcomes),
                eligibility=eligibility_for_candidate(spec),
                quality_state="ready",
                rank=None,
                created_at=moment + timedelta(minutes=5),
                completed_at=moment + timedelta(minutes=25),
            )
            for requirement in REQUIREMENTS:
                if requirement.kind == "ignored":
                    continue
                stable_id = requirement.stable_id
                if stable_id not in spec.outcomes:
                    continue
                outcome, reasoning = spec.outcomes[stable_id]
                block = _evidence_block(spec, stable_id)
                world.assessments.append(
                    RequirementAssessment(
                        id=f"demo-assessment-{spec.key}-{stable_id}",
                        evaluation_id=evaluation.id,
                        job_requirement_id=f"dj-{stable_id}",
                        outcome=outcome,
                        confidence=0.85,
                        reasoning=reasoning,
                        evidence=[
                            {
                                "blockId": block.id,
                                "quote": block.text,
                                "page": block.page,
                            }
                        ],
                        created_at=moment + timedelta(minutes=25),
                    )
                )
        world.candidates.append(record)
        world.documents.append(document)
        world.versions.append(version)
        world.submissions.append(submission)
        world.processing_jobs.append(processing)
        world.batch_submissions.append(batch_submission)
        world.evaluations.append(evaluation)
        world.files[f"demo/resumes/{spec.key}.txt"] = _resume_text(spec.blocks).encode()

    eligible_sorted = sorted(
        (e for e in world.evaluations if e.eligibility == "eligible"),
        key=lambda e: e.score or 0,
        reverse=True,
    )
    for rank, evaluation in enumerate(eligible_sorted, start=1):
        evaluation.rank = rank

    org_account = PointAccount(id="demo-account-org-points", organization_id=world.organization.id)
    user_account = PointAccount(id="demo-account-user-points", owner_user_id=candidate.id)
    world.point_accounts = [org_account, user_account]
    grant_time = base + timedelta(days=1)
    world.ledger_entries = [
        PointLedgerEntry(
            id="demo-ledger-org-grant",
            account_id=org_account.id,
            amount=5000,
            reason="Razorpay purchase scale-pack",
            idempotency_key="purchase:demo-scale-pack",
            created_at=grant_time,
        ),
        PointLedgerEntry(
            id="demo-ledger-org-settle",
            account_id=org_account.id,
            amount=-50,
            reason="Employer evaluation settlement",
            idempotency_key="settle:demo-batch-evaluation",
            created_at=grant_time + timedelta(hours=2),
        ),
        PointLedgerEntry(
            id="demo-ledger-user-grant",
            account_id=user_account.id,
            amount=500,
            reason="Razorpay purchase starter-pack",
            idempotency_key="purchase:demo-starter-pack",
            created_at=grant_time,
        ),
    ]

    candidate_base = now - timedelta(days=1)
    role_report_facts = {
        "skills": [
            {"canonicalName": "Python"},
            {"canonicalName": "Airflow"},
            {"canonicalName": "PostgreSQL"},
            {"canonicalName": "dbt"},
        ],
        "employment": [
            {
                "title": "Data Engineer",
                "employer": "Brightline Retail",
                "startDate": "2022-03",
                "endDate": None,
            }
        ],
        "education": [
            {
                "degree": "BEng",
                "fieldOfStudy": "Computer Science",
                "institution": "University of Leeds",
                "graduationDate": "2021",
            }
        ],
        "certifications": [],
        "warnings": [],
    }
    role_report = IndependentEvaluation(
        id="demo-independent-role-report",
        user_id=candidate.id,
        storage_key="demo/independent/jordan-resume.txt",
        original_name="jordan-blake-resume.txt",
        media_type="text/plain",
        job_description=(
            "Data Engineer III - Meridian Energy. Python and SQL daily, Airflow "
            "orchestration, dbt models, three years of experience required."
        ),
        status="complete",
        score=72,
        suggestions=[
            {
                "title": "Quantify your pipeline impact",
                "detail": (
                    "Your Airflow pipelines mention scale ('40 DAGs') but the dbt "
                    "models do not. Add row volumes or freshness targets they guarantee."
                ),
            },
            {
                "title": "Name your cloud explicitly",
                "detail": (
                    "'Cloud data warehouse' could be BigQuery, Snowflake, or Redshift. "
                    "Name it once near the top of the role."
                ),
            },
        ],
        improved_resume_key="demo/independent/jordan-corrected.docx",
        improved_resume_unlocked_at=candidate_base + timedelta(minutes=30),
        normalized_facts=role_report_facts,
        parser_version="demo",
        schema_version="demo",
        free_week_start=week_start(candidate_base),
        retention_date=now + _DEMO_RETENTION,
        created_at=candidate_base,
        completed_at=candidate_base + timedelta(minutes=20),
    )
    general_report = IndependentEvaluation(
        id="demo-independent-general-report",
        user_id=candidate.id,
        storage_key="demo/independent/jordan-resume-v2.txt",
        original_name="jordan-blake-resume-v2.txt",
        media_type="text/plain",
        job_description=None,
        status="complete",
        score=64,
        suggestions=[
            {
                "title": "Add dates to your freelance section",
                "detail": (
                    "Two entries have no start or end dates, so their duration "
                    "cannot be counted toward your experience."
                ),
            },
        ],
        improved_resume_key=None,
        normalized_facts={
            "skills": [{"canonicalName": "Python"}, {"canonicalName": "SQL"}],
            "employment": [],
            "education": [],
            "certifications": [],
            "warnings": [],
        },
        parser_version="demo",
        schema_version="demo",
        retention_date=now + _DEMO_RETENTION,
        created_at=candidate_base - timedelta(days=6),
        completed_at=candidate_base - timedelta(days=6) + timedelta(minutes=15),
    )
    world.independent_evaluations = [general_report, role_report]
    world.weekly_free_use = WeeklyFreeUse(
        id="demo-weekly-free-use",
        user_id=candidate.id,
        week_start=week_start(candidate_base),
        created_at=candidate_base,
    )

    jordan_resume = "\n\n".join(
        [
            "Jordan Blake - Data Engineer, Leeds UK",
            "Skills: Python, SQL, Airflow, dbt, BigQuery",
            "Data Engineer, Brightline Retail, 2022-03 to present. Built 40 "
            "Airflow DAGs feeding a cloud data warehouse and a dbt model layer.",
            "BEng Computer Science, University of Leeds, 2021",
        ]
    )
    world.files["demo/independent/jordan-resume.txt"] = jordan_resume.encode()
    world.files["demo/independent/jordan-resume-v2.txt"] = jordan_resume.encode()
    world.files["demo/independent/jordan-corrected.docx"] = _minimal_docx(
        jordan_resume.split("\n\n")
    )
    return world


async def ensure_demo_world(store: SQLAlchemyStore, settings: Settings) -> None:
    """Seed once under a PostgreSQL advisory lock; later calls are no-ops."""

    async with store.sessions().begin() as session:
        bind = session.get_bind()
        if bind.dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock))"),
                {"lock": DEMO_SEED_LOCK},
            )
        existing = (
            await session.execute(
                select(func.count()).select_from(User).where(User.is_demo.is_(True))
            )
        ).scalar_one()
        if existing:
            return
        world = build_demo_world(datetime.now(UTC))
        for group in _insert_groups(world):
            for row in group:
                session.add(row)
            await session.flush()

    storage = LocalObjectStorage(Path(settings.storage_root))
    for key, content in world.files.items():
        storage.put(key, content)


def _insert_groups(world: DemoWorld) -> list[list[object]]:
    return [
        list(world.users),
        list(world.accounts_auth),
        [world.organization] if world.organization else [],
        list(world.members),
        [world.job] if world.job else [],
        [world.job_version] if world.job_version else [],
        list(world.requirements),
        [world.batch_evaluation] if world.batch_evaluation else [],
        list(world.candidates),
        list(world.documents),
        list(world.versions),
        list(world.submissions),
        list(world.processing_jobs),
        # Evaluations carry a composite FK into batch_evaluation_submission,
        # so those link rows must exist before the evaluation rows.
        list(world.batch_submissions),
        list(world.evaluations),
        list(world.assessments),
        list(world.point_accounts),
        list(world.ledger_entries),
        list(world.independent_evaluations),
        [world.weekly_free_use] if world.weekly_free_use else [],
    ]
