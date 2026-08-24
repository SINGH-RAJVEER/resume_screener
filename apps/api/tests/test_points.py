from collections.abc import Sequence
from typing import cast

import pytest
from sqlalchemy import FromClause, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.persistence.models import Base, PointAccount, PointLedgerEntry, PointReservation
from app.persistence.points import InsufficientPointsError, PointLedger

POINT_TABLES: Sequence[FromClause] = [
    PointAccount.__table__,
    PointLedgerEntry.__table__,
    PointReservation.__table__,
]

pytestmark = pytest.mark.asyncio


async def make_ledger() -> tuple[PointLedger, str]:
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
    ledger = PointLedger(async_sessionmaker(engine, expire_on_commit=False))
    account = await ledger.user_account("user-1")
    return ledger, account.id


async def test_grant_increases_balance_and_is_idempotent() -> None:
    ledger, account_id = await make_ledger()

    first = await ledger.grant(account_id, 100, "purchase", "purchase-1")
    repeat = await ledger.grant(account_id, 100, "purchase", "purchase-1")
    second = await ledger.grant(account_id, 50, "purchase", "purchase-2")

    assert first == 100
    assert repeat == 100
    assert second == 150
    assert await ledger.available(account_id) == 150


async def test_reserve_holds_points_without_a_ledger_entry() -> None:
    ledger, account_id = await make_ledger()
    await ledger.grant(account_id, 100, "purchase", "purchase-1")

    reservation = await ledger.reserve(account_id, 60, "evaluation", "eval-1")

    assert reservation.state == "reserved"
    assert await ledger.available(account_id) == 40


async def test_reserve_rejects_amounts_above_the_available_balance() -> None:
    ledger, account_id = await make_ledger()

    with pytest.raises(InsufficientPointsError):
        await ledger.reserve(account_id, 1, "evaluation", "eval-1")


async def test_settlement_charges_at_most_the_reserved_maximum() -> None:
    ledger, account_id = await make_ledger()
    await ledger.grant(account_id, 100, "purchase", "purchase-1")
    reservation = await ledger.reserve(account_id, 80, "evaluation", "eval-1")

    await ledger.settle(reservation.id, 55, "evaluation charge")
    await ledger.settle(reservation.id, 20, "retry charge")

    assert await ledger.balance(account_id) == 45
    assert await ledger.available(account_id) == 45


async def test_release_returns_the_full_hold_without_charging() -> None:
    ledger, account_id = await make_ledger()
    await ledger.grant(account_id, 100, "purchase", "purchase-1")
    reservation = await ledger.reserve(account_id, 80, "evaluation", "eval-1")

    await ledger.release(reservation.id)

    assert await ledger.available(account_id) == 100


async def test_reservations_block_concurrent_spending_of_the_same_points() -> None:
    ledger, account_id = await make_ledger()
    await ledger.grant(account_id, 100, "purchase", "purchase-1")

    await ledger.reserve(account_id, 70, "evaluation", "eval-1")
    with pytest.raises(InsufficientPointsError):
        await ledger.reserve(account_id, 70, "evaluation", "eval-2")
