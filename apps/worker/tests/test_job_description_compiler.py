from typing import cast

from worker.job_descriptions.compiler import compile_job_description, source_blocks


def requirements(artifact: dict[str, object]) -> list[dict[str, object]]:
	return cast(list[dict[str, object]], artifact["requirements"])


def test_compiler_uses_sections_and_omits_non_requirements() -> None:
	artifact = compile_job_description(
		"""About us
We make accounting software.

Requirements
- Five years of Python experience
- PostgreSQL experience

Benefits
- Private health insurance
"""
	)

	drafts = requirements(artifact)
	assert [draft["normalizedText"] for draft in drafts] == [
		"Five years of Python experience",
		"PostgreSQL experience",
	]
	assert drafts[0]["suggestedKind"] == "required"
	assert drafts[0]["assessability"] == "resume_evidence"
	assert artifact["schemaVersion"] == "2"


def test_compiler_preserves_or_relationships() -> None:
	artifact = compile_job_description(
		"Requirements\n- Python or PostgreSQL experience"
	)
	predicate = cast(dict[str, object], requirements(artifact)[0]["predicate"])
	criteria = cast(list[dict[str, object]], predicate["criteria"])

	assert predicate["operator"] == "any_of"
	assert {criterion["canonicalName"] for criterion in criteria} == {
		"Python",
		"PostgreSQL",
	}


def test_compiler_does_not_promote_attestations_to_resume_evidence() -> None:
	artifact = compile_job_description(
		"Requirements\n- Must be authorized to work in India\n- Willing to work weekends"
	)
	drafts = requirements(artifact)

	assert [draft["assessability"] for draft in drafts] == [
		"candidate_attestation",
		"candidate_attestation",
	]
	assert all(draft["suggestedKind"] != "hard_gate" for draft in drafts)


def test_compiler_omits_protected_trait_criteria() -> None:
	artifact = compile_job_description(
		"Requirements\n- Must be under 35 years of age\n- Python experience"
	)

	assert [draft["normalizedText"] for draft in requirements(artifact)] == [
		"Python experience"
	]
	assert "Potentially prohibited criterion omitted" in cast(list[str], artifact["warnings"])[0]


def test_source_evidence_has_exact_offsets() -> None:
	source = "Requirements\n  - Must know Python\n"
	artifact = compile_job_description(source)
	evidence = cast(
		list[dict[str, object]],
		requirements(artifact)[0]["evidence"],
	)[0]
	start_offset = cast(int, evidence["startOffset"])
	end_offset = cast(int, evidence["endOffset"])

	assert source[start_offset:end_offset] == evidence["quote"]
	assert evidence["blockId"] == "jd-b1"
	assert source_blocks(source)[0].section == "requirements"


def test_grounded_model_output_is_fused_and_ungrounded_output_is_dropped() -> None:
	source = "Requirements\n- Experience building Python APIs"
	model_output: dict[str, object] = {
		"requirements": [
			{
				"normalizedText": "Python API development experience",
				"category": "skill",
				"suggestedKind": "required",
				"sourceModality": "section_required",
				"assessability": "resume_evidence",
				"predicate": {
					"operator": "all_of",
					"criteria": [
						{
							"type": "skill",
							"canonicalName": "python",
							"minimumMonths": None,
							"minimumLevel": None,
							"subjects": [],
						}
					],
				},
				"evidence": [
					{"blockId": "jd-b1", "quote": "Experience building Python APIs"}
				],
				"confidence": 0.9,
			},
			{
				"normalizedText": "Kubernetes experience",
				"category": "skill",
				"suggestedKind": "required",
				"sourceModality": "section_required",
				"assessability": "resume_evidence",
				"predicate": {
					"operator": "all_of",
					"criteria": [
						{
							"type": "skill",
							"canonicalName": "Kubernetes",
							"minimumMonths": None,
							"minimumLevel": None,
							"subjects": [],
						}
					],
				},
				"evidence": [{"blockId": "jd-b1", "quote": "not in source"}],
				"confidence": 0.9,
			},
		],
		"warnings": [],
	}

	artifact = compile_job_description(source, model_output)
	drafts = requirements(artifact)
	assert len(drafts) == 1
	assert cast(dict[str, object], drafts[0]["predicate"])["criteria"] == [
		{
			"type": "skill",
			"canonicalName": "Python",
			"minimumMonths": None,
			"minimumLevel": None,
			"subjects": [],
		}
	]
	assert "model" in cast(list[str], drafts[0]["signals"])
	assert any("ungrounded" in warning for warning in cast(list[str], artifact["warnings"]))
