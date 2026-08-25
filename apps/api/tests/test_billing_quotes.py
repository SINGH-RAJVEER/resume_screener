from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import FromClause, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.billing.quotes import (
	INDEPENDENT_QUOTE,
	UnknownQuoteKindError,
	point_quote,
	settle_points,
)
from app.billing.settings import BillingSettings, TaskBudget
from app.persistence.models import Base
from app.persistence.points import InsufficientPointsError, ensure_user_account

pytestmark = pytest.mark.asyncio


def make_settings(**overrides: object) -> BillingSettings:
	values: dict[str, object] = {
		"points_per_usd": 1000,
		"minimum_independent_evaluation_points": 10,
		"minimum_employer_resume_points": 5,
		"price_ceiling_usd_per_million_input": 3.0,
		"price_ceiling_usd_per_million_output": 15.0,
	}
	values.update(overrides)
	return BillingSettings(
		independent_budgets=(TaskBudget("extraction", 16_000, 4_096),),
		employer_budgets=(TaskBudget("extraction", 16_000, 4_096),),
		packs=(),
		**cast("dict[str, object]", values),  # type: ignore[arg-type]
	)


async def make_session():
	engine = create_async_engine(
		"sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
	)
	tables: Sequence[FromClause] = [
		Base.metadata.tables[name]
		for name in ("point_account", "point_ledger_entry", "point_reservation")
	]
	async with engine.begin() as connection:
		await connection.run_sync(
			lambda sync_connection: Base.metadata.create_all(
				sync_connection, tables=cast("Sequence[Table]", tables)
			)
		)
	return async_sessionmaker(engine, expire_on_commit=False)()


async def test_quote_uses_cost_ceiling_above_the_minimum() -> None:
	settings = make_settings()
	quote = point_quote(INDEPENDENT_QUOTE, settings)
	cost_usd = (16_000 * 3.0 + 4_096 * 15.0) / 1_000_000

	assert quote.cost_ceiling_points == -(-int(cost_usd * 1_000_000) // 1000)
	assert quote.points == max(settings.minimum_independent_evaluation_points, 110)
	assert quote.points == quote.cost_ceiling_points


async def test_minimum_charge_dominates_when_models_are_free() -> None:
	settings = make_settings(
		price_ceiling_usd_per_million_input=0.0,
		price_ceiling_usd_per_million_output=0.0,
	)

	assert point_quote(INDEPENDENT_QUOTE, settings).points == 10
	assert settle_points(None, INDEPENDENT_QUOTE, settings) == 10


async def test_settlement_uses_the_greater_of_reported_cost_and_minimum() -> None:
	settings = make_settings()

	assert settle_points(0.002, INDEPENDENT_QUOTE, settings) == 10
	assert settle_points(0.02, INDEPENDENT_QUOTE, settings) == 20


async def test_unknown_quote_kind_is_rejected() -> None:
	with pytest.raises(UnknownQuoteKindError):
		point_quote("unknown", make_settings())


async def test_reservation_idempotency_key_reuses_the_existing_hold() -> None:
	session = await make_session()
	account = await ensure_user_account(session, "user-1")
	await session.commit()

	from app.persistence.points import grant_in_session, reserve_in_session

	await grant_in_session(session, account.id, 100, "purchase", "purchase-1")
	first = await reserve_in_session(session, account.id, 40, "evaluation", "eval-1")
	await session.commit()
	try:
		await reserve_in_session(session, account.id, 90, "evaluation", "eval-1")
	except InsufficientPointsError:
		pytest.fail("Existing reservation should be reused without a balance check")

	repeat = await reserve_in_session(session, account.id, 90, "evaluation", "eval-1")
	await session.commit()

	assert repeat.id == first.id


async def test_week_start_is_monday_midnight_utc() -> None:
	from app.billing.allowance import next_reset, week_start

	wednesday = datetime(2026, 8, 26, 15, 30, tzinfo=UTC)
	assert week_start(wednesday) == datetime(2026, 8, 24, tzinfo=UTC)
	assert next_reset(wednesday) == datetime(2026, 8, 31, tzinfo=UTC)
	assert week_start(wednesday + timedelta(days=7)) == datetime(2026, 8, 31, tzinfo=UTC)
