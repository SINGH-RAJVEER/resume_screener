from worker.documents.normalizer import normalize_resume


def test_normalizes_exact_skill_aliases_with_evidence() -> None:
	facts = normalize_resume(
		[
			{"id": "p1-b1", "page": 1, "text": "Built APIs using Python and Postgres."},
			{"id": "p2-b1", "page": 2, "text": "Operated k8s clusters."},
		]
	)

	assert facts == {
		"contact": {"name": None, "email": None, "location": None},
		"skills": [
			{
				"canonicalName": "Kubernetes",
				"category": "Application server software",
				"evidenceBlockIds": ["p2-b1"],
			},
			{
				"canonicalName": "PostgreSQL",
				"category": "Object oriented data base management software",
				"evidenceBlockIds": ["p1-b1"],
			},
			{
				"canonicalName": "Python",
				"category": "Object or component oriented development software",
				"evidenceBlockIds": ["p1-b1"],
			},
		],
	}


def test_does_not_match_short_skill_names_inside_words() -> None:
	facts = normalize_resume([{"id": "p1-b1", "page": 1, "text": "Managed a staging system."}])

	assert facts == {"contact": {"name": None, "email": None, "location": None}, "skills": []}


def test_extracts_candidate_contact_facts() -> None:
	facts = normalize_resume(
		[
			{"id": "p1-b1", "page": 1, "text": "Ada Lovelace"},
			{"id": "p1-b2", "page": 1, "text": "ada@example.com"},
			{"id": "p1-b3", "page": 1, "text": "Location: Pune, India"},
		]
	)

	assert facts["contact"] == {
		"name": "Ada Lovelace",
		"email": "ada@example.com",
		"location": "Pune, India",
	}


def test_extracts_contact_from_single_document_block() -> None:
	# The parser emits TXT/DOCX resumes as one block holding the whole text.
	document = (
		"Ada Lovelace\nada@example.com\nLocation: Pune, India\n\nExperience\nBuilt APIs."
	)
	facts = normalize_resume([{"id": "p1-b1", "page": 1, "text": document}])

	assert facts["contact"] == {
		"name": "Ada Lovelace",
		"email": "ada@example.com",
		"location": "Pune, India",
	}
