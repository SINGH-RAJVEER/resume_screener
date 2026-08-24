"""Deterministic employment-interval arithmetic over extracted dates.

The extraction model may identify spans, but durations, overlaps, and
totals are computed here so score-relevant date math never depends on
model output.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast


@dataclass(frozen=True)
class MonthInterval:
	# Half-open span of calendar months as year * 12 + month indices.
	start: int
	end: int

	@property
	def months(self) -> int:
		return max(0, self.end - self.start)


@dataclass(frozen=True)
class EmploymentIntervals:
	valid: tuple[MonthInterval, ...]
	merged: tuple[MonthInterval, ...]
	overlap_count: int

	@property
	def total_months(self) -> int:
		return sum(interval.months for interval in self.merged)


def month_index(value: object) -> int | None:
	if not isinstance(value, str):
		return None
	parts = value.split("-")
	try:
		year = int(parts[0])
		month = int(parts[1]) if len(parts) > 1 else 1
	except ValueError:
		return None
	if not 1 <= month <= 12:
		return None
	return year * 12 + month


def employment_intervals(
	entries: object, *, now: datetime | None = None
) -> EmploymentIntervals:
	"""Build valid dated intervals from extracted employment facts.

	Entries without a start, with an end before their start, or otherwise
	unparsable dates are dropped rather than guessed. A current role
	without an end date runs to the reference month so totals stay
	deterministic for a given evaluation time.
	"""
	raw_entries = cast(list[object], entries) if isinstance(entries, list) else []
	reference = now or datetime.now(UTC)
	current_month = reference.year * 12 + reference.month
	valid: list[MonthInterval] = []
	for item in raw_entries:
		if not isinstance(item, Mapping):
			continue
		entry = cast(Mapping[str, Any], item)
		start = month_index(entry.get("startDate"))
		end = month_index(entry.get("endDate"))
		if end is None and entry.get("isCurrent") is True:
			end = current_month
		if start is None or end is None or end < start:
			continue
		valid.append(MonthInterval(start, end))
	return EmploymentIntervals(
		valid=tuple(valid),
		merged=tuple(_merged(valid)),
		overlap_count=sum(
			left.start <= right.end and right.start <= left.end
			for index, left in enumerate(valid)
			for right in valid[index + 1 :]
		),
	)


def _merged(intervals: Sequence[MonthInterval]) -> list[MonthInterval]:
	ordered = sorted(intervals, key=lambda interval: (interval.start, interval.end))
	merged: list[MonthInterval] = []
	for interval in ordered:
		if merged and interval.start <= merged[-1].end:
			previous = merged[-1]
			merged[-1] = MonthInterval(previous.start, max(previous.end, interval.end))
			continue
		merged.append(interval)
	return merged
