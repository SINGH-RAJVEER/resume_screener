from worker.evaluator import evaluate


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
