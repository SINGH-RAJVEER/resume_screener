from worker.evaluations.independent import independent_report


def test_independent_report_does_not_encourage_unsupported_skill_claims() -> None:
	_, suggestions = independent_report(
		{"contact": {"name": "Ada", "email": "ada@example.com"}, "skills": []},
		"Python and Docker experience",
	)

	assert any("only when your resume already supports" in str(item["detail"]) for item in suggestions)


def test_independent_report_scores_documented_basics() -> None:
	score, suggestions = independent_report(
		{
			"contact": {"name": "Ada", "email": "ada@example.com"},
			"skills": [{"canonicalName": "Python", "evidenceBlockIds": ["block-1"]}],
		},
		None,
	)

	assert score == 68
	assert suggestions == []
