from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, FromClause, Table, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth import AuthService
from app.core.config import Settings
from app.main import create_app
from app.persistence.models import (
	Base,
	IndependentEvaluation,
	Job,
	JobVersion,
	Organization,
	OrganizationMember,
	PointAccount,
	PointLedgerEntry,
	PointReservation,
	ProcessingJob,
	User,
	WeeklyFreeUse,
)
from app.persistence.store import SQLAlchemyStore, UserRecord

SECRET = "test-secret-that-is-at-least-32-characters"

UPLOAD_TABLES: Sequence[FromClause] = [
	User.__table__,
	Job.__table__,
	JobVersion.__table__,
	Organization.__table__,
	OrganizationMember.__table__,
	ProcessingJob.__table__,
	IndependentEvaluation.__table__,
	PointAccount.__table__,
	PointLedgerEntry.__table__,
	PointReservation.__table__,
	WeeklyFreeUse.__table__,
]

# The shared models use PostgreSQL JSONB, which has no SQLite renderer.
for _table in UPLOAD_TABLES:
	for _column in _table.columns:
		if isinstance(_column.type, JSONB):
			_column.type = _column.type.with_variant(JSON(), "sqlite")

pytestmark = pytest.mark.asyncio


def make_user(user_id: str, account_type: str) -> UserRecord:
	now = datetime.now(UTC)
	return UserRecord(user_id, "Ada", f"{user_id}@example.com", now, now, account_type)


@asynccontextmanager
async def upload_client(
	tmp_path: Path,
) -> AsyncGenerator[tuple[AsyncClient, SQLAlchemyStore]]:
	settings = Settings(
		database_url="postgresql://unused/skillsignal",
		web_url="http://localhost:3000",
		jwt_secret=SECRET,
		jwt_ttl=timedelta(days=1),
		storage_root=str(tmp_path / "storage"),
	)
	engine = create_async_engine(
		"sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
	)
	async with engine.begin() as connection:
		await connection.run_sync(
			lambda sync_connection: Base.metadata.create_all(
				# SQLAlchemy types __table__ as FromClause although create_all
				# receives concrete Table instances here.
				sync_connection,
				tables=cast("Sequence[Table]", UPLOAD_TABLES),
			)
		)
	store = SQLAlchemyStore(engine)
	transport = ASGITransport(app=create_app(store, settings))
	async with AsyncClient(transport=transport, base_url="http://test") as client:
		yield client, store
	await engine.dispose()


def auth_headers(store: SQLAlchemyStore, user: UserRecord) -> dict[str, str]:
	token = AuthService(store, SECRET, timedelta(hours=1)).issue_token(user).token
	return {"Authorization": f"Bearer {token}"}


async def seed_owner(store: SQLAlchemyStore, user_id: str = "owner-1") -> None:
	async with store.sessions().begin() as session:
		session.add(
			User(
				id=user_id,
				name="Owner",
				email=f"{user_id}@company.com",
				account_type="employer",
				created_at=datetime.now(UTC),
				updated_at=datetime.now(UTC),
			)
		)
		session.add(Organization(id="org-1", name="Company"))
		await session.flush()
		session.add(
			OrganizationMember(
				id="member-org-1",
				organization_id="org-1",
				user_id=user_id,
				role="owner",
			)
		)


async def seed_candidate(store: SQLAlchemyStore, user_id: str = "candidate-1") -> None:
	async with store.sessions().begin() as session:
		session.add(
			User(
				id=user_id,
				name="Candidate",
				email=f"{user_id}@example.com",
				account_type="candidate",
				created_at=datetime.now(UTC),
				updated_at=datetime.now(UTC),
			)
		)


async def stored_version(store: SQLAlchemyStore) -> JobVersion:
	async with store.sessions()() as session:
		version_id = (await session.execute(select(JobVersion.id))).scalars().first()
		version = await session.get(JobVersion, version_id)
	assert version is not None
	return version


async def test_employer_creates_a_job_from_an_uploaded_description_file(tmp_path: Path) -> None:
	async with upload_client(tmp_path) as (client, store):
		owner = make_user("owner-1", "employer")
		await seed_owner(store)
		response = await client.post(
			"/api/jobs",
			data={"organization_id": "org-1", "title": "Backend Engineer"},
			files={"file": ("role.txt", b"Grow the platform team\n", "text/plain")},
			headers=auth_headers(store, owner),
		)
		version = await stored_version(store)

	assert response.status_code == 202
	assert version.source_text is None
	assert version.source_storage_key is not None
	assert version.source_media_type == "text/plain"
	assert version.normalized_text is None


async def test_the_uploaded_description_file_is_stored_outside_the_database(tmp_path: Path) -> None:
	async with upload_client(tmp_path) as (client, store):
		owner = make_user("owner-1", "employer")
		await seed_owner(store)
		response = await client.post(
			"/api/jobs",
			data={"organization_id": "org-1", "title": "Backend Engineer"},
			files={"file": ("role.txt", b"Grow the platform team\n", "text/plain")},
			headers=auth_headers(store, owner),
		)
		version = await stored_version(store)
		assert version.source_storage_key is not None
		stored = Path(tmp_path / "storage" / version.source_storage_key)
		stored_content = stored.read_bytes()

	assert response.status_code == 202
	assert stored.is_file()
	assert stored_content == b"Grow the platform team\n"


async def test_job_creation_requires_a_description_or_a_file(tmp_path: Path) -> None:
	async with upload_client(tmp_path) as (client, store):
		owner = make_user("owner-1", "employer")
		await seed_owner(store)
		response = await client.post(
			"/api/jobs",
			data={"organization_id": "org-1", "title": "Backend Engineer"},
			headers=auth_headers(store, owner),
		)

	assert response.status_code == 400
	assert response.json()["message"] == "A job description is required"


async def test_job_creation_rejects_a_file_and_pasted_description_together(tmp_path: Path) -> None:
	async with upload_client(tmp_path) as (client, store):
		owner = make_user("owner-1", "employer")
		await seed_owner(store)
		response = await client.post(
			"/api/jobs",
			data={
				"organization_id": "org-1",
				"title": "Backend Engineer",
				"description": "Pasted text",
			},
			files={"file": ("role.txt", b"Uploaded text", "text/plain")},
			headers=auth_headers(store, owner),
		)

	assert response.status_code == 400
	assert "not both" in response.json()["message"]


async def test_candidate_uploads_a_job_description_file_with_their_resume(tmp_path: Path) -> None:
	async with upload_client(tmp_path) as (client, store):
		candidate = make_user("candidate-1", "candidate")
		await seed_candidate(store)
		response = await client.post(
			"/api/independent-evaluations",
			data={},
			files=[
				("file", ("resume.txt", b"Resume text", "text/plain")),
				("job_description_file", ("role.txt", b"Role text", "text/plain")),
			],
			headers=auth_headers(store, candidate),
		)
		evaluation_id = response.json()["id"]
		async with store.sessions()() as session:
			evaluation = await session.get(IndependentEvaluation, evaluation_id)

	assert response.status_code == 202
	assert evaluation is not None
	assert evaluation.job_description is None
	assert evaluation.job_description_key is not None
	assert evaluation.job_description_key.startswith("independent-job-descriptions/")
	assert evaluation.job_description_media_type == "text/plain"
	stored = Path(tmp_path / "storage" / str(evaluation.job_description_key))
	assert stored.read_bytes() == b"Role text"


async def test_independent_evaluation_rejects_a_description_file_and_text_together(
	tmp_path: Path,
) -> None:
	async with upload_client(tmp_path) as (client, store):
		candidate = make_user("candidate-1", "candidate")
		await seed_candidate(store)
		response = await client.post(
			"/api/independent-evaluations",
			data={"job_description": "Pasted role text"},
			files=[
				("file", ("resume.txt", b"Resume text", "text/plain")),
				("job_description_file", ("role.txt", b"Role text", "text/plain")),
			],
			headers=auth_headers(store, candidate),
		)

	assert response.status_code == 400
	assert "not both" in response.json()["message"]


async def test_processing_job_is_queued_for_an_uploaded_description(tmp_path: Path) -> None:
	async with upload_client(tmp_path) as (client, store):
		owner = make_user("owner-1", "employer")
		await seed_owner(store)
		response = await client.post(
			"/api/jobs",
			data={"organization_id": "org-1", "title": "Backend Engineer"},
			files={"file": ("role.pdf", b"%PDF-1.7\n", "application/pdf")},
			headers=auth_headers(store, owner),
		)
		body = response.json()
		async with store.sessions()() as session:
			job = await session.get(ProcessingJob, body["processingJobId"])

	assert job is not None
	assert job.type == "job_description_processing"
