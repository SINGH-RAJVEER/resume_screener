from worker.evaluations.evaluator import assess_requirement, evaluate


def requirement(text: str, requirement_id: str = "req-1") -> dict[str, object]:
	return {
		"id": requirement_id,
		"kind": "required",
		"weight": 2,
		"normalized_text": text,
	}


def facts(
	employment: list[object] | None = None,
	certifications: list[object] | None = None,
	education: list[object] | None = None,
) -> dict[str, object]:
	return {
		"skills": [],
		"employment": employment or [],
		"certifications": certifications or [],
		"education": education or [],
	}


def test_years_requirement_met_from_dated_employment() -> None:
	result = assess_requirement(
		requirement("At least 3 years of backend experience"),
		{},
		facts(employment=[
			{"startDate": "2019-01", "endDate": "2024-01", "isCurrent": False},
		]),
	)
	assert result.outcome == "met"


def test_years_requirement_partial_on_shortfall() -> None:
	result = assess_requirement(
		requirement("5 years of experience"),
		{},
		facts(employment=[
			{"startDate": "2022-06", "endDate": None, "isCurrent": True},
		]),
	)
	assert result.outcome in {"partial", "not_met", "unknown"}


def test_years_requirement_unknown_without_dates() -> None:
	result = assess_requirement(
		requirement("7 years of experience"),
		{},
		facts(employment=[{"employer": "Example"}]),
	)
	assert result.outcome == "unknown"


def test_certification_requirement_matches_documented_name() -> None:
	# "AWS" alone is a corpus skill, so use a credential phrase the
	# vocabulary does not cover to exercise the certification matcher.
	result = assess_requirement(
		requirement("Solutions Architect certification required"),
		{},
		facts(certifications=[{"name": "AWS Solutions Architect"}]),
	)
	assert result.outcome == "met"
	assert result.evidence[0]["quote"] == "AWS Solutions Architect"


def test_certification_absent_is_unknown() -> None:
	# The requirement names no documented credential and mentions no
	# corpus skill, so there is nothing deterministic to judge.
	result = assess_requirement(
		requirement("PMP certification preferred"),
		{},
		facts(certifications=[]),
	)
	assert result.outcome == "unknown"


def test_education_level_matching() -> None:
	met = assess_requirement(
		requirement("Master degree in computer science"),
		{},
		facts(education=[{"degree": "M.Sc Computer Science"}]),
	)
	assert met.outcome == "met"

	partial = assess_requirement(
		requirement("PhD in a related field"),
		{},
		facts(education=[{"degree": "B.Tech Computer Engineering"}]),
	)
	assert partial.outcome == "partial"


def test_skills_still_take_priority() -> None:
	result = assess_requirement(
		requirement("Python with 10 years of experience"),
		{"Python": ["p1-b1"]},
		facts(employment=[]),
	)
	assert result.outcome == "met"


def test_overlapping_intervals_are_merged() -> None:
	from worker.evaluations.evaluator import employment_months

	months = employment_months([
		{"startDate": "2020-01", "endDate": "2021-01", "isCurrent": False},
		{"startDate": "2020-06", "endDate": "2022-01", "isCurrent": False},
	])
	# 2020-01 to 2022-01 is 24 months of merged coverage.
	assert months is not None and 22 <= months <= 26


def test_aggregate_uses_extended_assessments() -> None:
	result = evaluate(
		facts(
			employment=[
				{"startDate": "2020-01", "endDate": "2024-01", "isCurrent": False}
			]
		),
		[
			requirement("4 years of experience", "r1"),
			requirement("Comfortable with our on-call rotation culture", "r2"),
		],
	)
	# r2 has no deterministic signal and stays unknown, so it drops out of
	# the weighted average instead of dragging the score down.
	assert result.score == 100
