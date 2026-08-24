from worker.evaluations.evaluator import evaluate


def test_scores_explicit_skill_evidence_and_hard_gates() -> None:
	result = evaluate(
		{"skills": [{"canonicalName": "Python", "evidenceBlockIds": ["p1-b1"]}]},
		[
			{
				"id": "python",
				"kind": "required",
				"weight": 2,
				"normalized_text": "Python experience",
			},
			{
				"id": "kubernetes",
				"kind": "hard_gate",
				"weight": 1,
				"normalized_text": "Kubernetes experience",
			},
		],
	)

	assert result.score == 100
	assert result.evidence_coverage == 100
	assert result.eligibility == "needs_review"
	assert result.assessments[0].outcome == "met"
	assert result.assessments[1].outcome == "unknown"


def test_scores_partial_multi_skill_requirement() -> None:
	result = evaluate(
		{"skills": [{"canonicalName": "Python", "evidenceBlockIds": ["p1-b1"]}]},
		[
			{
				"id": "backend",
				"kind": "required",
				"weight": 2,
				"normalized_text": "Python and PostgreSQL experience",
			}
		],
	)

	assert result.score == 50
	assert result.assessments[0].outcome == "partial"
	assert result.assessments[0].evidence == [{"blockId": "p1-b1", "quote": "Python"}]


def test_typed_any_of_requirement_accepts_one_documented_path() -> None:
	result = evaluate(
		{"skills": [{"canonicalName": "Python", "evidenceBlockIds": ["p1-b1"]}]},
		[
			{
				"id": "backend",
				"kind": "required",
				"weight": 2,
				"normalized_text": "Python or Go experience",
				"assessability": "resume_evidence",
				"predicate": {
					"operator": "any_of",
					"criteria": [
						{"type": "skill", "canonicalName": "Python"},
						{"type": "skill", "canonicalName": "Go"},
					],
				},
			}
		],
	)

	assert result.assessments[0].outcome == "met"
	assert result.score == 100


def test_relevant_experience_duration_stays_unknown_without_dated_subject_evidence() -> None:
	result = evaluate(
		{
			"skills": [{"canonicalName": "Python", "evidenceBlockIds": ["p1-b1"]}],
			"employment": [
				{"startDate": "2010-01", "endDate": "2020-01", "isCurrent": False}
			],
		},
		[
			{
				"id": "experience",
				"kind": "required",
				"weight": 2,
				"normalized_text": "Five years of Python experience",
				"assessability": "resume_evidence",
				"predicate": {
					"operator": "all_of",
					"criteria": [
						{
							"type": "experience",
							"minimumMonths": 60,
							"subjects": ["Python"],
						}
					],
				},
			}
		],
	)

	assert result.assessments[0].outcome == "unknown"
	assert result.score is None


def test_higher_education_level_satisfies_lower_minimum() -> None:
	result = evaluate(
		{"skills": [], "education": [{"degree": "PhD in Computer Science"}]},
		[
			{
				"id": "degree",
				"kind": "required",
				"weight": 1,
				"normalized_text": "Bachelor degree",
				"assessability": "resume_evidence",
				"predicate": {
					"operator": "all_of",
					"criteria": [
						{"type": "education", "minimumLevel": "bachelor"}
					],
				},
			}
		],
	)

	assert result.assessments[0].outcome == "met"


def test_candidate_attestation_never_enters_resume_proof() -> None:
	result = evaluate(
		{"skills": []},
		[
			{
				"id": "travel",
				"kind": "hard_gate",
				"weight": 1,
				"normalized_text": "Willing to travel",
				"assessability": "candidate_attestation",
			}
		],
	)

	assert result.assessments[0].outcome == "unknown"
	assert result.eligibility == "needs_review"
