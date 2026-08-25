from collections.abc import Sequence
from typing import cast

import pytest
from sqlalchemy import FromClause, Table
from sqlalchemy.ext.asyncio import (
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.persistence.models import Base, PointAccount, PointLedgerEntry, PointReservation
from app.persistence.points import (
	InsufficientPointsError,
	available_balance,
	balance,
	ensure_user_account,
	grant_in_session,
	release_in_session,
	reserve_in_session,
	settle_in_session,
)

POINT_TABLES: Sequence[FromClause] = [
    PointAccount.__table__,
    PointLedgerEntry.__table__,
    PointReservation.__table__,
]

pytestmark = pytest.mark.asyncio


async def make_ledger() -> tuple[async_sessionmaker[AsyncSession], str]:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                # SQLAlchemy types __table__ as FromClause although create_all
                # receives concrete Table instances here.
                sync_connection,
                tables=cast("Sequence[Table]", POINT_TABLES),
            )
        )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        account = await ensure_user_account(session, "user-1")
    return sessions, account.id


async def grant(sessions: async_sessionmaker[AsyncSession], *args: object) -> int:
    async with sessions.begin() as session:
        return await grant_in_session(session, *args)  # type: ignore[arg-type]


async def reserve(sessions: async_sessionmaker[AsyncSession], *args: object):
    async with sessions.begin() as session:
        return await reserve_in_session(session, *args)  # type: ignore[arg-type]


async def settle(
    sessions: async_sessionmaker[AsyncSession], reservation_id: str, amount: int, reason: str
) -> None:
    async with sessions.begin() as session:
        await settle_in_session(session, reservation_id, amount, reason)


async def release(sessions: async_sessionmaker[AsyncSession], reservation_id: str) -> None:
    async with sessions.begin() as session:
        await release_in_session(session, reservation_id)


async def current_balance(sessions: async_sessionmaker[AsyncSession], account_id: str) -> int:
    async with sessions() as session:
        return await balance(session, account_id)


async def available(sessions: async_sessionmaker[AsyncSession], account_id: str) -> int:
    async with sessions() as session:
        return await available_balance(session, account_id)


async def test_grant_increases_balance_and_is_idempotent() -> None:
    sessions, account_id = await make_ledger()

    first = await grant(sessions, account_id, 100, "purchase", "purchase-1")
    repeat = await grant(sessions, account_id, 100, "purchase", "purchase-1")
    second = await grant(sessions, account_id, 50, "purchase", "purchase-2")

    assert first == 100
    assert repeat == 100
    assert second == 150
    assert await available(sessions, account_id) == 150


async def test_reserve_holds_points_without_a_ledger_entry() -> None:
    sessions, account_id = await make_ledger()
    await grant(sessions, account_id, 100, "purchase", "purchase-1")

    reservation = await reserve(sessions, account_id, 60, "evaluation", "eval-1")

    assert reservation.state == "reserved"
    assert await available(sessions, account_id) == 40


async def test_reserve_rejects_amounts_above_the_available_balance() -> None:
    sessions, account_id = await make_ledger()

    with pytest.raises(InsufficientPointsError):
        await reserve(sessions, account_id, 1, "evaluation", "eval-1")


async def test_settlement_charges_at_most_the_reserved_maximum() -> None:
    sessions, account_id = await make_ledger()
    await grant(sessions, account_id, 100, "purchase", "purchase-1")
    reservation = await reserve(sessions, account_id, 80, "evaluation", "eval-1")

    await settle(sessions, reservation.id, 55, "evaluation charge")
    await settle(sessions, reservation.id, 20, "retry charge")

    assert await current_balance(sessions, account_id) == 45
    assert await available(sessions, account_id) == 45


async def test_release_returns_the_full_hold_without_charging() -> None:
    sessions, account_id = await make_ledger()
    await grant(sessions, account_id, 100, "purchase", "purchase-1")
    reservation = await reserve(sessions, account_id, 80, "evaluation", "eval-1")

    await release(sessions, reservation.id)

    assert await available(sessions, account_id) == 100


async def test_reservations_block_concurrent_spending_of_the_same_points() -> None:
    sessions, account_id = await make_ledger()
    await grant(sessions, account_id, 100, "purchase", "purchase-1")

    await reserve(sessions, account_id, 70, "evaluation", "eval-1")
    with pytest.raises(InsufficientPointsError):
        await reserve(sessions, account_id, 70, "evaluation", "eval-2")
