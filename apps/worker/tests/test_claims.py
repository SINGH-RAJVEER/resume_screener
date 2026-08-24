from worker.extraction.claims import measure_unsupported_claims

BLOCKS = {
	"b0": "Ada Lovelace\nada@example.com",
	"b1": "Skills: Python, PostgreSQL, Kubernetes",
	"b2": "Senior Platform Engineer at Example Corp, 2020 to 2025",
	"b3": "Certified: AWS Solutions Architect",
}

FACTS = {
	"contact": {
		"name": "Ada Lovelace",
		"email": "ada@example.com",
		"evidence": [
			{"blockId": "b0", "quote": "Ada Lovelace\nada@example.com"}
		],
	},
	"skills": [
		{
			"canonicalName": "Python",
			"sourceText": "Python",
			"evidence": [{"blockId": "b1", "quote": "Python"}],
		},
		{
			# Schema-valid but invented: no cited block contains Go.
			"canonicalName": "Go",
			"sourceText": "Go",
			"evidence": [{"blockId": "b1", "quote": "Python"}],
		},
	],
	"employment": [
		{
			"employer": "Example Corp",
			"title": "Senior Platform Engineer",
			"startDate": "2020-01",
			"endDate": "2025-01",
			"isCurrent": False,
			"evidence": [{"blockId": "b2", "quote": "Senior Platform Engineer at Example Corp"}],
		},
	],
	"education": [
		{
			# Citation points to a block that does not contain the quote.
			"institution": "Example University",
			"degree": "BSc Computer Science",
			"evidence": [{"blockId": "b1", "quote": "Example University"}],
		}
	],
	"certifications": [
		{
			"name": "AWS Solutions Architect",
			"evidence": [{"blockId": "b3", "quote": "AWS Solutions Architect"}],
		}
	],
}


def test_supported_claims_are_not_counted() -> None:
	report = measure_unsupported_claims(FACTS, BLOCKS)
	assert report.total_claims == 11
	# Only the invented skill and the mis-cited education entry are unsupported.
	assert report.unsupported_claims == 4


def test_invented_values_count_as_ungrounded() -> None:
	report = measure_unsupported_claims(FACTS, BLOCKS)
	skills = report.collections["skills"]
	assert skills.total == 4
	assert skills.ungrounded_values == 2  # canonical name and source text
	assert any("skills.canonicalName: Go" in example for example in report.examples)


def test_citations_missing_from_source_count_as_invalid() -> None:
	report = measure_unsupported_claims(FACTS, BLOCKS)
	education = report.collections["education"]
	assert education.invalid_citations == 2
	assert education.ungrounded_values == 0


def test_empty_artifacts_yield_no_rate() -> None:
	assert measure_unsupported_claims({}, BLOCKS).rate is None
	assert measure_unsupported_claims(FACTS, {}).rate == 1.0
