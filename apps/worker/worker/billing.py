from dataclasses import dataclass
from secrets import token_urlsafe

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True)
class BillingSettings:
	"""Mirrors the API deployment configuration for point economics."""

	points_per_usd: int = 1000
	minimum_independent_evaluation_points: int = 10
	minimum_employer_resume_points: int = 5
	price_ceiling_usd_per_million_input: float = 3.0
	price_ceiling_usd_per_million_output: float = 15.0


def settle_points(
	prompt_tokens: int,
	completion_tokens: int,
	reported_cost_usd: float,
	kind: str,
	settings: BillingSettings,
) -> int:
	"""Completion charge: the greater of the applicable minimum or the
	ceiling-rounded reported cost. Unreported cost falls back to token
	counts priced at the configured ceilings."""

	from math import ceil

	minimum = (
		settings.minimum_independent_evaluation_points
		if kind == "independent_evaluation"
		else settings.minimum_employer_resume_points
	)
	cost = reported_cost_usd
	if cost <= 0:
		cost = (
			prompt_tokens * settings.price_ceiling_usd_per_million_input
			+ completion_tokens * settings.price_ceiling_usd_per_million_output
		) / 1_000_000
	return max(minimum, ceil(cost * settings.points_per_usd))


async def settle_reservation(
	connection: AsyncConnection, reservation_id: str, charged_points: int, reason: str
) -> None:
	"""Charge at most the reserved amount and close the reservation.

	Idempotent: a reservation that is not open anymore is left untouched.
	"""

	row = (
		await connection.execute(
			text(
				"""
				SELECT account_id, amount FROM point_reservation
				WHERE id = :id AND state = 'reserved' FOR UPDATE
				"""
			),
			{"id": reservation_id},
		)
	).mappings().one_or_none()
	if row is None:
		return
	charge = min(charged_points, int(row["amount"]))
	await connection.execute(
		text(
			"""
			INSERT INTO point_ledger_entry (id, account_id, amount, reason, idempotency_key)
			VALUES (:id, :account_id, :amount, :reason, :idempotency_key)
			ON CONFLICT (account_id, idempotency_key) DO NOTHING
			"""
		),
		{
			"id": token_urlsafe(18),
			"account_id": row["account_id"],
			"amount": -charge,
			"reason": reason,
			"idempotency_key": f"settle:{reservation_id}",
		},
	)
	await connection.execute(
		text(
			"UPDATE point_reservation SET state = 'settled', updated_at = now() "
			"WHERE id = :id"
		),
		{"id": reservation_id},
	)


async def release_evaluation_reservations(
	connection: AsyncConnection, where_clause: str, params: dict[str, object]
) -> None:
	"""Release unsettled holds for evaluations matched by the given clause."""

	await connection.execute(
		text(
			f"""
			UPDATE point_reservation SET state = 'released', updated_at = now()
			WHERE state = 'reserved'
				AND id IN (
					SELECT evaluation.point_reservation_id FROM evaluation
					WHERE evaluation.point_reservation_id IS NOT NULL
						AND {where_clause}
				)
			"""
		),
		params,
	)
