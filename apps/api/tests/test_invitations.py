from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth import AuthService
from app.core.config import Settings
from app.main import create_app
from app.persistence.models import (
	Base,
	Invitation,
	Job,
	Organization,
	User,
)
from app.persistence.store import SQLAlchemyStore, UserRecord

SECRET = "test-secret-that-is-at-least-32-characters"

SETTINGS = Settings(
	database_url="postgresql://unused/skillsignal",
	web_url="http://localhost:3000",
	jwt_secret=SECRET,
	jwt_ttl=timedelta(days=1),
)

INVITATION_TABLES: Sequence[Table] = [
	Base.metadata.tables[name] for name in ("user", "organization", "job", "invitation")
]

pytestmark = pytest.mark.asyncio

TOKEN = "tok-" + "a" * 60
PASSCODE = "AB12CD34"
TOKEN_HASH = sha256(TOKEN.encode()).hexdigest()
PASSCODE_HASH = sha256(PASSCODE.encode()).hexdigest()


@asynccontextmanager
async def invitation_client(
	tmp_path: Path,
) -> AsyncGenerator[tuple[AsyncClient, SQLAlchemyStore]]:
	settings = replace(SETTINGS, storage_root=str(tmp_path / "storage"))
	engine = create_async_engine(
		"sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
	)
	async with engine.begin() as connection:
		await connection.run_sync(
			lambda sync_connection: Base.metadata.create_all(
				sync_connection, tables=list(INVITATION_TABLES)
			)
		)
	store = SQLAlchemyStore(engine)
	transport = ASGITransport(app=create_app(store, settings))
	async with AsyncClient(transport=transport, base_url="http://test") as client:
		yield client, store
	await engine.dispose()


def candidate_headers(store: SQLAlchemyStore, user_id: str) -> dict[str, str]:
	now = datetime.now(UTC)
	record = UserRecord(user_id, "Ada", f"{user_id}@example.com", now, now, "candidate")
	token = AuthService(store, SECRET, timedelta(hours=1)).issue_token(record).token
	return {"Authorization": f"Bearer {token}"}


async def seed_open_job_invitation(
	store: SQLAlchemyStore,
	*,
	expires_in: timedelta | None = None,
	revoked: bool = False,
) -> Invitation:
	"""Seed an open job with a single-use invitation and return it."""

	async with store.sessions().begin() as session:
		session.add(
			User(id="candidate-1", name="Ada", email="candidate-1@example.com")
		)
		session.add(
			User(id="candidate-2", name="Grace", email="candidate-2@example.com")
		)
		session.add(Organization(id="org-1", name="Org"))
		window_start = datetime.now(UTC) - timedelta(days=1)
		session.add(
			Job(
				id="job-1",
				organization_id="org-1",
				title="Engineer",
				application_opens_at=window_start,
				application_closes_at=window_start + timedelta(days=8),
			)
		)
		invitation = Invitation(
			id="invite-1",
			job_id="job-1",
			creator_user_id="creator-1",
			token_hash=TOKEN_HASH,
			passcode_hash=PASSCODE_HASH,
			expires_at=datetime.now(UTC) + (expires_in or timedelta(days=1)),
			revoked_at=datetime.now(UTC) if revoked else None,
		)
		session.add(invitation)
	return invitation


async def invitation_state(store: SQLAlchemyStore) -> tuple[str | None, str | None]:
	async with store.sessions()() as session:
		row = (await session.execute(select(Invitation))).scalar_one()
		return row.redeeming_user_id, row.resume_submission_id


async def test_token_redeem_is_single_use_across_users(tmp_path: Path) -> None:
	async with invitation_client(tmp_path) as (client, store):
		await seed_open_job_invitation(store)
		first = await client.post(
			f"/api/invitations/{TOKEN}/redeem",
			headers=candidate_headers(store, "candidate-1"),
		)
		assert first.status_code == 200, first.text
		second = await client.post(
			f"/api/invitations/{TOKEN}/redeem",
			headers=candidate_headers(store, "candidate-2"),
		)

		assert first.json() == {"jobId": "job-1", "invitationId": "invite-1"}
		assert second.status_code == 409, second.text
		assert second.json()["code"] == "INVITATION_REDEEMED"
		redeeming_user, submission = await invitation_state(store)
		assert redeeming_user == "candidate-1"
		assert submission is None


async def test_passcode_redeem_normalizes_input(tmp_path: Path) -> None:
	async with invitation_client(tmp_path) as (client, store):
		await seed_open_job_invitation(store)
		response = await client.post(
			"/api/invitations/redeem",
			json={"passcode": f"  {PASSCODE.lower()}  "},
			headers=candidate_headers(store, "candidate-1"),
		)

		assert response.status_code == 200, response.text
		assert response.json() == {"jobId": "job-1", "invitationId": "invite-1"}
		redeeming_user, _submission = await invitation_state(store)
		assert redeeming_user == "candidate-1"


async def test_redeem_rejects_unknown_expired_and_revoked(tmp_path: Path) -> None:
	async with invitation_client(tmp_path / "unknown") as (client, store):
		await seed_open_job_invitation(store)
		unknown = await client.post(
			f"/api/invitations/{'x' * 63}/redeem",
			headers=candidate_headers(store, "candidate-1"),
		)

	async with invitation_client(tmp_path / "expired") as (client, store):
		await seed_open_job_invitation(store, expires_in=timedelta(hours=-1))
		expired = await client.post(
			f"/api/invitations/{TOKEN}/redeem",
			headers=candidate_headers(store, "candidate-1"),
		)

	async with invitation_client(tmp_path / "revoked") as (client, store):
		await seed_open_job_invitation(store, revoked=True)
		revoked = await client.post(
			f"/api/invitations/{TOKEN}/redeem",
			headers=candidate_headers(store, "candidate-1"),
		)

	assert unknown.status_code == 404
	assert expired.status_code == 404
	assert revoked.status_code == 404


async def test_passcode_redeem_is_single_use_across_users(tmp_path: Path) -> None:
	async with invitation_client(tmp_path) as (client, store):
		await seed_open_job_invitation(store)
		first = await client.post(
			"/api/invitations/redeem",
			json={"passcode": PASSCODE},
			headers=candidate_headers(store, "candidate-1"),
		)
		second = await client.post(
			"/api/invitations/redeem",
			json={"passcode": PASSCODE},
			headers=candidate_headers(store, "candidate-2"),
		)

	assert first.status_code == 200
	assert second.status_code == 409
