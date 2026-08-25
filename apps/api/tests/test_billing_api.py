import hashlib
import hmac
import json
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, MetaData, Table, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth import AuthService
from app.billing.settings import BillingSettings, TaskBudget
from app.core.config import Settings
from app.main import create_app
from app.persistence.models import (
	Base,
	IndependentEvaluation,
	Organization,
	OrganizationEntitlement,
	PointAccount,
	PointLedgerEntry,
	PointReservation,
	ProcessingJob,
	RazorpayOrder,
	RazorpayPayment,
	RazorpayWebhookEvent,
	User,
	WeeklyFreeUse,
)
from app.persistence.store import SQLAlchemyStore, UserRecord

SECRET = "test-secret-that-is-at-least-32-characters"
WEBHOOK_SECRET = "whsec-test-secret"

BILLING = BillingSettings(
	independent_budgets=(TaskBudget("extraction", 16_000, 4_096),),
	employer_budgets=(TaskBudget("extraction", 16_000, 4_096),),
	packs=(),
	points_per_usd=1000,
	minimum_independent_evaluation_points=10,
	minimum_employer_resume_points=5,
	razorpay_key_id="rzp_test_key",
	razorpay_key_secret="rzp_test_secret",
	razorpay_webhook_secret=WEBHOOK_SECRET,
	admin_token="admin-token-1",
)

# Copies keep the PostgreSQL-JSONB-to-SQLite type variant local to this
# module instead of mutating the shared ORM metadata other tests import.
# Organization is copied only so foreign keys resolve inside the private
# metadata; SQLite does not require the referenced table to exist.
_BILLING_METADATA = MetaData()
_COPIED = [
	table.to_metadata(_BILLING_METADATA)
	for table in (
		User.__table__,
		Organization.__table__,
		OrganizationEntitlement.__table__,
		IndependentEvaluation.__table__,
		ProcessingJob.__table__,
		PointAccount.__table__,
		PointLedgerEntry.__table__,
		PointReservation.__table__,
		WeeklyFreeUse.__table__,
		RazorpayOrder.__table__,
		RazorpayPayment.__table__,
		RazorpayWebhookEvent.__table__,
	)
]
_BY_NAME = {table.name: table for table in _COPIED}
BILLING_TABLES: Sequence[Table] = [
	_BY_NAME[name]
	for name in (
		"user",
		"independent_evaluation",
		"processing_job",
		"point_account",
		"point_ledger_entry",
		"point_reservation",
		"weekly_free_use",
		"razorpay_order",
		"razorpay_payment",
		"razorpay_webhook_event",
		"organization_entitlement",
	)
]

# The shared models use PostgreSQL JSONB, which has no SQLite renderer.
for _table in BILLING_TABLES:
	for _column in _table.columns:
		if isinstance(_column.type, JSONB):
			_column.type = _column.type.with_variant(JSON(), "sqlite")

pytestmark = pytest.mark.asyncio


def make_user(user_id: str, account_type: str) -> UserRecord:
	now = datetime.now(UTC)
	return UserRecord(user_id, "Ada", f"{user_id}@example.com", now, now, account_type)


@asynccontextmanager
async def billing_client(tmp_path: Path) -> AsyncGenerator[tuple[AsyncClient, SQLAlchemyStore]]:
	settings = Settings(
		database_url="postgresql://unused/skillsignal",
		web_url="http://localhost:3000",
		jwt_secret=SECRET,
		jwt_ttl=timedelta(days=1),
		storage_root=str(tmp_path / "storage"),
		billing=BILLING,
	)
	engine = create_async_engine(
		"sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
	)
	async with engine.begin() as connection:
		await connection.run_sync(
			lambda sync_connection: Base.metadata.create_all(
				sync_connection, tables=cast("Sequence[Table]", BILLING_TABLES)
			)
		)
	store = SQLAlchemyStore(engine)
	transport = ASGITransport(app=create_app(store, settings))
	async with AsyncClient(transport=transport, base_url="http://test") as client:
		yield client, store
	await engine.dispose()


def auth_headers(store: SQLAlchemyStore, user_id: str) -> dict[str, str]:
	user_record = make_user(user_id, "candidate")
	token = AuthService(store, SECRET, timedelta(hours=1)).issue_token(user_record).token
	return {"Authorization": f"Bearer {token}"}


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


async def ledger_amounts(store: SQLAlchemyStore) -> list[int]:
	async with store.sessions()() as session:
		account_id = (
			await session.execute(select(PointAccount.id).limit(1))
		).scalar_one_or_none()
		if account_id is None:
			return []
		rows = await session.execute(
			select(PointLedgerEntry.amount).where(PointLedgerEntry.account_id == account_id)
		)
		return list(rows.scalars())


async def upload_resume(client: AsyncClient, headers: dict[str, str]) -> dict[str, object]:
	response = await client.post(
		"/api/independent-evaluations",
		data={},
		files={"file": ("resume.txt", b"Resume text", "text/plain")},
		headers=headers,
	)
	assert response.status_code == 202, response.text
	return cast("dict[str, object]", response.json())


async def test_the_first_weekly_evaluation_is_free_and_the_next_needs_points(
	tmp_path: Path,
) -> None:
	async with billing_client(tmp_path) as (client, store):
		headers = auth_headers(store, "candidate-1")
		await seed_candidate(store)

		first = await upload_resume(client, headers)
		second_response = await client.post(
			"/api/independent-evaluations",
			data={},
			files={"file": ("resume.txt", b"Resume text", "text/plain")},
			headers=headers,
		)
		amounts = await ledger_amounts(store)

	# The free evaluation reserves nothing and charges nothing yet.
	assert first["freeEvaluation"] is True
	assert first["reservedPoints"] == 0
	assert amounts == []
	assert second_response.status_code == 402
	assert second_response.json()["code"] == "INSUFFICIENT_POINTS"


async def test_a_purchased_balance_reserves_the_quoted_maximum(tmp_path: Path) -> None:
	async with billing_client(tmp_path) as (client, store):
		headers = auth_headers(store, "candidate-1")
		await seed_candidate(store)
		async with store.sessions().begin() as session:
			account = PointAccount(id="acct-1", owner_user_id="candidate-1")
			session.add(account)
			session.add(
				PointLedgerEntry(
					id="entry-1",
					account_id=account.id,
					amount=1000,
					reason="purchase",
					idempotency_key="purchase-1",
				)
			)

		# The first evaluation consumes the weekly free allowance even with a
		# balance; the second one must reserve quoted points.
		await upload_resume(client, headers)
		first = await upload_resume(client, headers)
		reservations = (
			(
				await store.sessions()()
				.execute(select(PointReservation.amount, PointReservation.state))
			)
			.all()
		)
		amounts = await ledger_amounts(store)

	quote_points = 110  # (16k * $3 + 4k * $15) / 1M * 1000 points/USD, rounded up
	assert first["freeEvaluation"] is False
	assert first["reservedPoints"] == quote_points
	assert reservations == [(quote_points, "reserved")]
	assert sorted(amounts) == [1000]


async def test_deleting_a_paid_evaluation_releases_the_open_hold(tmp_path: Path) -> None:
	async with billing_client(tmp_path) as (client, store):
		headers = auth_headers(store, "candidate-1")
		await seed_candidate(store)
		async with store.sessions().begin() as session:
			session.add(PointAccount(id="acct-1", owner_user_id="candidate-1"))
			session.add(
				PointLedgerEntry(
					id="entry-1",
					account_id="acct-1",
					amount=1000,
					reason="purchase",
					idempotency_key="purchase-1",
				)
			)

		await upload_resume(client, headers)  # consumes the weekly free evaluation
		paid = await upload_resume(client, headers)
		evaluation_id = cast("str", paid["id"])
		deleted = await client.delete(
			f"/api/independent-evaluations/{evaluation_id}", headers=headers
		)
		released_states = (
			(await store.sessions()().execute(select(PointReservation.state))).scalars().all()
		)
		retry = await upload_resume(client, headers)
		final_states = (
			(await store.sessions()().execute(select(PointReservation.state))).scalars().all()
		)

	assert deleted.status_code == 204
	assert released_states == ["released"]
	# The returned hold funds another evaluation instead of stranding points.
	assert retry.status_code == 202
	assert final_states == ["released", "reserved"]


async def test_deleting_a_settled_evaluation_never_touches_the_ledger(tmp_path: Path) -> None:
	async with billing_client(tmp_path) as (client, store):
		headers = auth_headers(store, "candidate-1")
		await seed_candidate(store)
		async with store.sessions().begin() as session:
			session.add(PointAccount(id="acct-1", owner_user_id="candidate-1"))
			session.add(
				PointLedgerEntry(
					id="entry-1",
					account_id="acct-1",
					amount=1000,
					reason="purchase",
					idempotency_key="purchase-1",
				)
			)

		await upload_resume(client, headers)  # consumes the weekly free evaluation
		paid = await upload_resume(client, headers)
		async with store.sessions().begin() as session:
			reservation = (
				await session.execute(select(PointReservation))
			).scalar_one()
			assert reservation.state == "reserved"
			reservation.state = "settled"
		deleted = await client.delete(
			f"/api/independent-evaluations/{cast('str', paid['id'])}",
			headers=headers,
		)
		amounts = await ledger_amounts(store)

	assert deleted.status_code == 204
	assert amounts == [1000]


async def test_webhook_capture_grants_points_once_and_refunds_compensate(
	tmp_path: Path,
) -> None:
	async with billing_client(tmp_path) as (client, store):
		await seed_candidate(store)
		async with store.sessions().begin() as session:
			session.add(
				RazorpayOrder(
					id="local-order-1",
					razorpay_order_id="order_test_1",
					account_id="acct-1",
					purchaser_user_id="candidate-1",
					pack_id="pack-500",
					points=500,
					amount_inr=499,
				)
			)
			session.add(PointAccount(id="acct-1", owner_user_id="candidate-1"))

		event = {
			"event": "payment.captured",
			"payload": {
				"payment": {
					"entity": {
						"id": "pay_1",
						"order_id": "order_test_1",
						"status": "captured",
						"method": "upi",
						"amount": 49900,
					}
				}
			},
		}

		def signed(body: dict[str, object]) -> tuple[dict[str, str], str]:
			raw = json.dumps(body).encode()
			signature = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
			return {"X-Razorpay-Signature": signature}, raw.decode()

		header, payload = signed(event)
		captured = await client.post("/api/webhooks/razorpay", content=payload, headers=header)
		duplicate = await client.post("/api/webhooks/razorpay", content=payload, headers=header)
		assert captured.status_code == 200
		assert duplicate.status_code == 200

		refund_event = {
			"event": "refund.processed",
			"payload": {
				"refund": {"entity": {"id": "rfnd_1", "amount": 49900}},
				"payment": {
					"entity": {
						"id": "pay_1",
						"order_id": "order_test_1",
						"status": "refunded",
						"amount": 49900,
					}
				},
			},
		}
		refund_header, refund_payload = signed(refund_event)
		refunded = await client.post(
			"/api/webhooks/razorpay", content=refund_payload, headers=refund_header
		)
		assert refunded.status_code == 200

		assert sorted(await ledger_amounts(store)) == [-500, 500]

		payments = (
			(await store.sessions()().execute(select(RazorpayPayment)))
			.scalars()
			.all()
		)
		assert len(payments) == 1
		assert payments[0].points_granted is True
		assert payments[0].refunded_inr == 499


async def test_checkout_verification_records_but_never_grants(tmp_path: Path) -> None:
	async with billing_client(tmp_path) as (client, store):
		headers = auth_headers(store, "candidate-1")
		await seed_candidate(store)
		async with store.sessions().begin() as session:
			session.add(
				RazorpayOrder(
					id="local-order-1",
					razorpay_order_id="order_test_1",
					account_id="acct-1",
					purchaser_user_id="candidate-1",
					pack_id="pack-500",
					points=500,
					amount_inr=499,
				)
			)
			session.add(PointAccount(id="acct-1", owner_user_id="candidate-1"))

		payment_id = "pay_browser_1"
		signature = hmac.new(
			b"rzp_test_secret", b"order_test_1|" + payment_id.encode(), hashlib.sha256
		).hexdigest()
		valid = await client.post(
			"/api/billing/orders/local-order-1/verify",
			json={
				"razorpay_payment_id": payment_id,
				"razorpay_signature": signature,
			},
			headers=headers,
		)
		forged = await client.post(
			"/api/billing/orders/local-order-1/verify",
			json={
				"razorpay_payment_id": "pay_other",
				"razorpay_signature": "00" * 32,
			},
			headers=headers,
		)
		amounts = await ledger_amounts(store)

	assert valid.status_code == 200
	assert forged.status_code == 400
	assert forged.json()["code"] == "INVALID_SIGNATURE"
	# Browser callbacks never grant points by themselves.
	assert amounts == []


async def test_unsigned_webhooks_are_rejected(tmp_path: Path) -> None:
	async with billing_client(tmp_path) as (client, store):
		response = await client.post("/api/webhooks/razorpay", content=b"{}")
		amounts = await ledger_amounts(store)

	assert response.status_code == 400
	assert response.json()["code"] == "INVALID_SIGNATURE"
	assert amounts == []


async def test_admin_entitlement_provisioning_requires_the_operator_token(
	tmp_path: Path,
) -> None:
	async with billing_client(tmp_path) as (client, _store):
		denied = await client.post(
			"/api/admin/organizations/org-1/entitlement", json={"note": ""}
		)
		granted = await client.post(
			"/api/admin/organizations/org-1/entitlement",
			json={"note": "annual contract"},
			headers={"X-Admin-Token": "admin-token-1"},
		)
		repeated = await client.post(
			"/api/admin/organizations/org-1/entitlement",
			json={"note": ""},
			headers={"X-Admin-Token": "admin-token-1"},
		)
		revoked = await client.delete(
			"/api/admin/organizations/org-1/entitlement",
			headers={"X-Admin-Token": "admin-token-1"},
		)

	assert denied.status_code == 404
	assert granted.status_code == 201
	assert repeated.status_code == 409
	assert revoked.status_code == 204


async def test_points_endpoint_reports_balance_and_allowance_reset(tmp_path: Path) -> None:
	async with billing_client(tmp_path) as (client, store):
		headers = auth_headers(store, "candidate-1")
		await seed_candidate(store)
		async with store.sessions().begin() as session:
			session.add(
				PointAccount(id="acct-1", owner_user_id="candidate-1")
			)
			session.add(
				PointLedgerEntry(
					id="entry-1",
					account_id="acct-1",
					amount=250,
					reason="purchase",
					idempotency_key="purchase-1",
				)
			)

		payload = await client.get("/api/me/points", headers=headers)
		history = await client.get("/api/billing/ledger", headers=headers)

	body = payload.json()
	assert body["balance"] == 250
	assert body["available"] == 250
	assert body["allowance"]["freeUsedThisWeek"] is False
	assert body["allowance"]["resetsAt"]
	assert history.json() == [
		{"amount": 250, "reason": "purchase", "createdAt": history.json()[0]["createdAt"]}
	]
