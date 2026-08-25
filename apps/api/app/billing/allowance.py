from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..persistence.models import WeeklyFreeUse


def week_start(now: datetime) -> datetime:
	"""Calendar-week boundary used by the free allowance: Monday 00:00 UTC."""

	moment = now.astimezone(UTC)
	monday = moment - timedelta(days=moment.weekday())
	return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def next_reset(now: datetime) -> datetime:
	return week_start(now) + timedelta(days=7)


async def claim_free_week(
	session: AsyncSession, user_id: str, now: datetime
) -> datetime | None:
	"""Reserve this calendar week's free evaluation for the user.

	Returns the claimed week start, or None when the user already used the
	non-accumulating weekly allowance. The unique constraint makes concurrent
	submissions pick exactly one winner.
	"""

	start = week_start(now)
	taken = (
		await session.execute(
			select(WeeklyFreeUse.id).where(
				(WeeklyFreeUse.user_id == user_id) & (WeeklyFreeUse.week_start == start)
			)
		)
	).scalar_one_or_none()
	if taken is not None:
		return None
	session.add(WeeklyFreeUse(id=token_urlsafe(18), user_id=user_id, week_start=start))
	return start
