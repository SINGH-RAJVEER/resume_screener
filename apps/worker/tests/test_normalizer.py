from worker.documents.normalizer import normalize_resume


def test_normalizes_exact_skill_aliases_with_evidence() -> None:
	facts = normalize_resume(
		[
			{"id": "p1-b1", "page": 1, "text": "Built APIs using Python and Postgres."},
			{"id": "p2-b1", "page": 2, "text": "Operated k8s clusters."},
		]
	)

	assert facts == {
		"skills": [
			{"canonicalName": "Kubernetes", "evidenceBlockIds": ["p2-b1"]},
			{"canonicalName": "PostgreSQL", "evidenceBlockIds": ["p1-b1"]},
			{"canonicalName": "Python", "evidenceBlockIds": ["p1-b1"]},
		]
	}


def test_does_not_match_short_skill_names_inside_words() -> None:
	facts = normalize_resume([{"id": "p1-b1", "page": 1, "text": "Managed a staging system."}])

	assert facts == {"skills": []}
