from datetime import UTC, datetime

from worker.evaluations.intervals import employment_intervals, month_index


def test_month_index_parses_year_and_year_month() -> None:
	assert month_index("2020-03") == 2020 * 12 + 3
	# Year-only dates resolve to January of that year.
	assert month_index("2020") == 2020 * 12 + 1
	assert month_index("not-a-date") is None
	assert month_index("2020-13") is None
	assert month_index(None) is None


def test_computes_per_interval_durations() -> None:
	intervals = employment_intervals([
		{"startDate": "2019-01", "endDate": "2021-01", "isCurrent": False},
	])
	assert intervals.valid[0].months == 24


def test_current_role_runs_to_reference_month() -> None:
	intervals = employment_intervals(
		[{"startDate": "2024-06", "endDate": None, "isCurrent": True}],
		now=datetime(2026, 8, 1, tzinfo=UTC),
	)
	assert intervals.total_months == 26


def test_counts_overlapping_entry_pairs() -> None:
	intervals = employment_intervals([
		{"startDate": "2020-01", "endDate": "2021-01", "isCurrent": False},
		{"startDate": "2020-06", "endDate": "2022-01", "isCurrent": False},
	])
	assert intervals.overlap_count == 1
	assert [interval.months for interval in intervals.merged] == [24]


def test_totals_merge_overlaps_once() -> None:
	intervals = employment_intervals([
		{"startDate": "2018-01", "endDate": "2020-01", "isCurrent": False},
		{"startDate": "2019-06", "endDate": "2021-06", "isCurrent": False},
		{"startDate": "2023-01", "endDate": "2024-01", "isCurrent": False},
	])
	assert intervals.overlap_count == 1
	assert intervals.total_months == 53


def test_drops_entries_without_usable_dates() -> None:
	intervals = employment_intervals([
		{"employer": "Undated Corp"},
		{"startDate": "2020-05", "endDate": "2020-02", "isCurrent": False},
		{"startDate": "bad", "endDate": "2021-01", "isCurrent": False},
		{"startDate": "2020-01", "endDate": "2020-04", "isCurrent": False},
	])
	assert len(intervals.valid) == 1
	assert intervals.overlap_count == 0
	assert intervals.total_months == 3


def test_empty_facts_produce_no_intervals() -> None:
	assert employment_intervals([]).total_months == 0
	assert employment_intervals(None).valid == ()
