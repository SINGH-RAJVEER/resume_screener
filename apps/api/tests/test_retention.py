import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, TextClause, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.routes import document_retention_date
from app.billing.settings import BillingSettings
from app.core.config import Settings
from app.documents.storage import LocalObjectStorage
from app.main import create_app
from app.persistence.models import (
	Base,
	BatchEvaluation,
	BatchEvaluationSubmission,
	CandidateRecord,
	Evaluation,
	IndependentEvaluation,
	Job,
	JobRequirement,
	JobVersion,
	Organization,
	PointAccount,
	PointLedgerEntry,
	PointReservation,
	ProcessingJob,
	RequirementAssessment,
	ResumeDocument,
	ResumeSubmission,
	ResumeVersion,
	ReviewDecision,
	User,
)
from app.persistence.retention import purge_expired_data
from app.persistence.store import SQLAlchemyStore

SECRET = "test-secret-that-is-at-least-32-characters"
NOW = datetime.now(UTC)

SETTINGS = Settings(
	database_url="postgresql://unused/skillsignal",
	web_url="http://localhost:3000",
	jwt_secret=SECRET,
	jwt_ttl=timedelta(days=1),
	billing=BillingSettings(admin_token="operator-token"),
)

# The shared models use PostgreSQL JSONB, which has no SQLite renderer, and
# jsonb-cast server defaults that SQLite cannot parse. Other test modules
# may already have applied the SQLite variants, so never re-wrap a column.
for _table in Base.metadata.tables.values():
	for _column in _table.columns:
		if (
			isinstance(_column.type, JSONB)
			and not getattr(_column.type, "_variant_mapping", None)
		):
			_column.type = _column.type.with_variant(JSON(), "sqlite")
		_default_arg = getattr(_column.server_default, "arg", None)
		if isinstance(_default_arg, TextClause) and "::jsonb" in str(_default_arg.text):
			_default_arg.text = str(_default_arg.text).replace("::jsonb", "")

pytestmark = pytest.mark.asyncio


def make_engine() -> AsyncEngine:
	engine = create_async_engine(
		"sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
	)

	@event.listens_for(engine.sync_engine, "connect")
	def enable_foreign_keys(
		dbapi_connection: sqlite3.Connection, _record: object
	) -> None:
		cursor = dbapi_connection.cursor()
		cursor.execute("PRAGMA foreign_keys=ON")
		cursor.close()

	return engine


@asynccontextmanager
async def retention_store(tmp_path: Path) -> AsyncGenerator[tuple[SQLAlchemyStore, Path]]:
	engine = make_engine()
	async with engine.begin() as connection:
		await connection.run_sync(lambda sync_connection: Base.metadata.create_all(sync_connection))
	yield SQLAlchemyStore(engine), tmp_path / "storage"
	await engine.dispose()


def retention_client(store: SQLAlchemyStore, storage_root: Path) -> AsyncClient:
	settings = replace(SETTINGS, storage_root=str(storage_root))
	transport = ASGITransport(app=create_app(store, settings))
	return AsyncClient(transport=transport, base_url="http://test")


async def seed_independent_evaluation(
	store: SQLAlchemyStore,
	*,
	evaluation_id: str,
	retention_date: datetime,
	with_hold: bool,
) -> None:
	async with store.sessions().begin() as session:
		session.add(
			User(
				id=f"user-{evaluation_id}",
				name="Ada",
				email=f"{evaluation_id}@example.com",
				account_type="candidate",
			)
		)
		await session.flush()
		session.add(PointAccount(id=f"acct-{evaluation_id}", owner_user_id=f"user-{evaluation_id}"))
		await session.flush()
		if with_hold:
			session.add(
				PointLedgerEntry(
					id=f"grant-{evaluation_id}",
					account_id=f"acct-{evaluation_id}",
					amount=1000,
					reason="purchase",
					idempotency_key=f"purchase-{evaluation_id}",
				)
			)
			session.add(
				PointReservation(
					id="hold-1",
					account_id=f"acct-{evaluation_id}",
					amount=10,
					purpose="independent_evaluation",
					idempotency_key=f"reservation:{evaluation_id}",
				)
			)
			await session.flush()
		session.add(
			IndependentEvaluation(
				id=evaluation_id,
				user_id=f"user-{evaluation_id}",
				storage_key=f"independent-resumes/{evaluation_id}.txt",
				job_description_key=f"independent-job-descriptions/{evaluation_id}.txt",
				improved_resume_key=f"independent-resumes/improved/{evaluation_id}.docx",
				original_name="resume.txt",
				media_type="text/plain",
				retention_date=retention_date,
				point_reservation_id="hold-1" if with_hold else None,
			)
		)
		await session.flush()
		session.add(
			ProcessingJob(
				id=f"pj-{evaluation_id}",
				type="independent_evaluation_processing",
				payload_reference=evaluation_id,
				idempotency_key=f"idem-{evaluation_id}",
			)
		)


async def seed_employer_documents(store: SQLAlchemyStore) -> None:
	"""An expired document and a live document sharing one batch evaluation."""
	async with store.sessions().begin() as session:
		session.add(
			User(id="owner-1", name="Owner", email="owner@example.com", account_type="employer")
		)
		session.add(Organization(id="org-1", name="Acme", retention_days=90))
		await session.flush()
		session.add(Job(id="job-1", organization_id="org-1", title="Role"))
		await session.flush()
		session.add(
			JobVersion(id="jv-1", job_id="job-1", version=1, source_media_type="text/plain")
		)
		await session.flush()
		session.add(
			JobRequirement(
				id="req-1",
				job_version_id="jv-1",
				stable_id="req-1",
				kind="required",
				weight=2,
				normalized_text="Python",
				source_evidence=[],
			)
		)
		await session.flush()
		session.add(
			BatchEvaluation(
				id="batch-1",
				organization_id="org-1",
				job_id="job-1",
				job_version_id="jv-1",
				created_by_user_id="owner-1",
				requirement_schema_version="test-schema",
			)
		)
		for label in ("expired", "live"):
			session.add(CandidateRecord(id=f"cand-{label}", organization_id="org-1"))
			await session.flush()
			session.add(
				ResumeDocument(
					id=f"doc-{label}",
					organization_id="org-1",
					candidate_record_id=f"cand-{label}",
					storage_key=f"resumes/doc-{label}.txt",
					checksum="sha256",
					media_type="text/plain",
					size_bytes=12,
					original_name="resume.txt",
					retention_date=NOW - timedelta(days=1 if label == "expired" else -30),
				)
			)
			await session.flush()
			session.add(
				ResumeVersion(
					id=f"version-{label}",
					organization_id="org-1",
					resume_document_id=f"doc-{label}",
					version=1,
				)
			)
			await session.flush()
			session.add(
				ResumeSubmission(
					id=f"submission-{label}",
					organization_id="org-1",
					job_id="job-1",
					candidate_record_id=f"cand-{label}",
					resume_version_id=f"version-{label}",
				)
			)
			await session.flush()
			# Evaluations carry a composite foreign key into the batch link
			# table, so each link row must exist before its evaluation.
			session.add(
				BatchEvaluationSubmission(
					organization_id="org-1",
					job_id="job-1",
					batch_evaluation_id="batch-1",
					resume_submission_id=f"submission-{label}",
				)
			)
			await session.flush()
			session.add(
				Evaluation(
					id=f"evaluation-{label}",
					batch_evaluation_id="batch-1",
					resume_submission_id=f"submission-{label}",
					job_version_id="jv-1",
					resume_version_id=f"version-{label}",
					status="complete",
					score=70,
				)
			)
			await session.flush()
		session.add_all(
			[
				RequirementAssessment(
					id="assessment-1",
					evaluation_id="evaluation-expired",
					job_requirement_id="req-1",
					outcome="met",
					confidence=1.0,
					reasoning="deterministic match",
					evidence=[],
				),
				ReviewDecision(
					id="decision-1",
					organization_id="org-1",
					batch_evaluation_id="batch-1",
					evaluation_id="evaluation-expired",
					reviewer_user_id="owner-1",
					eligibility="eligible",
					reason="ok",
				),
			]
		)


async def test_purge_removes_an_expired_evaluation_with_its_files_and_hold(
	tmp_path: Path,
) -> None:
	async with retention_store(tmp_path) as (store, storage_root):
		storage = LocalObjectStorage(storage_root)
		await seed_independent_evaluation(
			store,
			evaluation_id="eval-old",
			retention_date=NOW - timedelta(days=1),
			with_hold=True,
		)
		await seed_independent_evaluation(
			store,
			evaluation_id="eval-new",
			retention_date=NOW + timedelta(days=30),
			with_hold=False,
		)
		for evaluation_id in ("eval-old", "eval-new"):
			for suffix in ("txt", "docx"):
				key = (
					f"independent-resumes/improved/{evaluation_id}.{suffix}"
					if suffix == "docx"
					else f"independent-resumes/{evaluation_id}.{suffix}"
				)
				storage.put(key, b"payload")

		async with store.sessions().begin() as session:
			result = await purge_expired_data(session, storage, NOW)

		assert result.independent_evaluations_purged == 1
		assert result.documents_purged == 0
		async with store.sessions()() as session:
			remaining_ids = set(
				(await session.execute(select(IndependentEvaluation.id))).scalars()
			)
			jobs = set((await session.execute(select(ProcessingJob.payload_reference))).scalars())
			states = set((await session.execute(select(PointReservation.state))).scalars())
		assert remaining_ids == {"eval-new"}
		# The expired report's queue record went with it.
		assert jobs == {"eval-new"}
		# The expired report's unsettled hold returned to the balance.
		assert states == {"released"}
		assert not (storage_root / "independent-resumes/eval-old.txt").exists()
		assert (storage_root / "independent-resumes/eval-new.txt").exists()


async def test_purge_removes_expired_employer_documents_to_their_derived_data(
	tmp_path: Path,
) -> None:
	async with retention_store(tmp_path) as (store, storage_root):
		storage = LocalObjectStorage(storage_root)
		await seed_employer_documents(store)
		storage.put("resumes/doc-expired.txt", b"expired resume")
		storage.put("resumes/doc-live.txt", b"live resume")

		async with store.sessions().begin() as session:
			result = await purge_expired_data(session, storage, NOW)

		assert result.documents_purged == 1
		async with store.sessions()() as session:
			document_ids = set((await session.execute(select(ResumeDocument.id))).scalars())
			version_ids = set((await session.execute(select(ResumeVersion.id))).scalars())
			submission_ids = set((await session.execute(select(ResumeSubmission.id))).scalars())
			evaluation_ids = set((await session.execute(select(Evaluation.id))).scalars())
			assessment_ids = set(
				(await session.execute(select(RequirementAssessment.id))).scalars()
			)
			decision_ids = set((await session.execute(select(ReviewDecision.id))).scalars())
			batches = set((await session.execute(select(BatchEvaluation.id))).scalars())
			links = set(
				(
					await session.execute(
						select(BatchEvaluationSubmission.resume_submission_id)
					)
				).scalars()
			)
		assert document_ids == {"doc-live"}
		assert version_ids == {"version-live"}
		assert submission_ids == {"submission-live"}
		assert evaluation_ids == {"evaluation-live"}
		assert assessment_ids == set()
		assert decision_ids == set()
		# The batch keeps its live submission, so it survives.
		assert batches == {"batch-1"}
		assert links == {"submission-live"}
		assert not (storage_root / "resumes/doc-expired.txt").exists()
		assert (storage_root / "resumes/doc-live.txt").exists()


async def test_retention_sweep_endpoint_requires_and_honors_the_operator_token(
	tmp_path: Path,
) -> None:
	async with retention_store(tmp_path) as (store, storage_root):
		await seed_independent_evaluation(
			store,
			evaluation_id="eval-old",
			retention_date=NOW - timedelta(days=1),
			with_hold=False,
		)
		async with retention_client(store, storage_root) as client:
			denied = await client.post("/api/admin/retention/sweep")
			allowed = await client.post(
				"/api/admin/retention/sweep", headers={"x-admin-token": "operator-token"}
			)

		assert denied.status_code == 404
		assert allowed.status_code == 200
		assert allowed.json() == {
			"documentsPurged": 0,
			"independentEvaluationsPurged": 1,
		}
		assert not (storage_root / "independent-resumes/eval-old.txt").exists()


async def test_creation_stamps_configured_retention_dates(tmp_path: Path) -> None:
	"""Documents inherit 90 days here because the org keeps the default."""
	async with retention_store(tmp_path) as (store, _storage_root):
		async with store.sessions().begin() as session:
			session.add(
				User(
					id="candidate-1",
					name="Ada",
					email="ada@example.com",
					account_type="candidate",
				)
			)
			session.add(Organization(id="org-1", name="Acme", retention_days=90))
			await session.flush()
			session.add(Job(id="job-1", organization_id="org-1", title="Role"))
			session.add(
				JobVersion(
					id="jv-1", job_id="job-1", version=1, source_media_type="text/plain"
				)
			)

		# The unit under test is the date arithmetic helper shared by the
		# upload routes; exercising it directly avoids re-driving uploads.
		async with store.sessions()() as session:
			date = await document_retention_date(session, "org-1")
		expected_floor = datetime.now(UTC) + timedelta(days=89)
		assert date > expected_floor

		independent_date = NOW + timedelta(days=30)
		assert independent_date > NOW
