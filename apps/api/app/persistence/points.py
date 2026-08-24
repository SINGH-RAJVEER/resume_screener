from datetime import UTC, datetime
from secrets import token_urlsafe

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import PointAccount, PointLedgerEntry, PointReservation


class InsufficientPointsError(Exception):
	pass


class ReservationStateError(Exception):
	pass


def _new_id() -> str:
	return token_urlsafe(18)


class PointLedger:
	"""Immutable point accounting over accounts, ledger entries, and reservations.

	Balance is the sum of ledger entries. A reservation holds part of the
	balance without touching the ledger; settlement charges a single negative
	entry and closes the reservation, release returns the hold untouched.
	"""

	def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
		self._sessions = sessions

	async def user_account(self, owner_user_id: str) -> PointAccount:
		async with self._sessions.begin() as session:
			return await _ensure_account(session, owner_user_id=owner_user_id)

	async def organization_account(self, organization_id: str) -> PointAccount:
		async with self._sessions.begin() as session:
			return await _ensure_account(session, organization_id=organization_id)

	async def grant(
		self, account_id: str, amount: int, reason: str, idempotency_key: str
	) -> int:
		if amount <= 0:
			raise ValueError("Grant amounts must be positive")
		async with self._sessions.begin() as session:
			await _account_for_update(session, account_id)
			existing = await session.execute(
				select(PointLedgerEntry).where(
					(PointLedgerEntry.account_id == account_id)
					& (PointLedgerEntry.idempotency_key == idempotency_key)
				)
			)
			if existing.scalar_one_or_none() is not None:
				return await balance(session, account_id)
			session.add(
				PointLedgerEntry(
					id=_new_id(),
					account_id=account_id,
					amount=amount,
					reason=reason,
					idempotency_key=idempotency_key,
				)
			)
			return await balance(session, account_id)

	async def available(self, account_id: str) -> int:
		async with self._sessions() as session:
			return await available_balance(session, account_id)

	async def balance(self, account_id: str) -> int:
		async with self._sessions() as session:
			return await balance(session, account_id)

	async def reserve(
		self, account_id: str, amount: int, purpose: str, idempotency_key: str
	) -> PointReservation:
		if amount <= 0:
			raise ValueError("Reservation amounts must be positive")
		async with self._sessions.begin() as session:
			existing = (
				await session.execute(
					select(PointReservation).where(
						(PointReservation.account_id == account_id)
						& (PointReservation.idempotency_key == idempotency_key)
					)
				)
			).scalar_one_or_none()
			if existing is not None:
				return existing
			await _account_for_update(session, account_id)
			if await available_balance(session, account_id) < amount:
				raise InsufficientPointsError
			reservation = PointReservation(
				id=_new_id(),
				account_id=account_id,
				amount=amount,
				purpose=purpose,
				idempotency_key=idempotency_key,
				created_at=datetime.now(UTC),
				updated_at=datetime.now(UTC),
			)
			session.add(reservation)
			return reservation

	async def settle(
		self, reservation_id: str, charged_amount: int, reason: str
	) -> None:
		if charged_amount <= 0:
			raise ValueError("Settled charges must be positive")
		async with self._sessions.begin() as session:
			reservation = await _reservation_for_update(session, reservation_id)
			if reservation.state != "reserved":
				return
			charge = min(charged_amount, reservation.amount)
			session.add(
				PointLedgerEntry(
					id=_new_id(),
					account_id=reservation.account_id,
					amount=-charge,
					reason=reason,
					idempotency_key=f"settle:{reservation.id}",
				)
			)
			reservation.state = "settled"
			reservation.updated_at = datetime.now(UTC)

	async def release(self, reservation_id: str) -> None:
		async with self._sessions.begin() as session:
			reservation = await _reservation_for_update(session, reservation_id)
			if reservation.state != "reserved":
				return
			reservation.state = "released"
			reservation.updated_at = datetime.now(UTC)


async def balance(session: AsyncSession, account_id: str) -> int:
	total = await session.execute(
		select(func.coalesce(func.sum(PointLedgerEntry.amount), 0)).where(
			PointLedgerEntry.account_id == account_id
		)
	)
	return int(total.scalar_one())


async def reserved(session: AsyncSession, account_id: str) -> int:
	total = await session.execute(
		select(func.coalesce(func.sum(PointReservation.amount), 0)).where(
			(PointReservation.account_id == account_id)
			& (PointReservation.state == "reserved")
		)
	)
	return int(total.scalar_one())


async def available_balance(session: AsyncSession, account_id: str) -> int:
	return await balance(session, account_id) - await reserved(session, account_id)


async def _ensure_account(
	session: AsyncSession,
	*, owner_user_id: str | None = None, organization_id: str | None = None
) -> PointAccount:
	assert (owner_user_id is None) != (organization_id is None)
	column = PointAccount.owner_user_id if owner_user_id else PointAccount.organization_id
	value = owner_user_id or organization_id
	existing = (
		await session.execute(select(PointAccount).where(column == value))
	).scalar_one_or_none()
	if existing is not None:
		return existing
	account = PointAccount(
		id=_new_id(), owner_user_id=owner_user_id, organization_id=organization_id
	)
	session.add(account)
	await session.flush()
	return account


async def _account_for_update(session: AsyncSession, account_id: str) -> PointAccount:
	account = (
		await session.execute(
			select(PointAccount).where(PointAccount.id == account_id).with_for_update()
		)
	).scalar_one()
	return account


async def _reservation_for_update(
	session: AsyncSession, reservation_id: str
) -> PointReservation:
	reservation = (
		await session.execute(
			select(PointReservation).where(PointReservation.id == reservation_id).with_for_update()
		)
	).scalar_one()
	return reservation
