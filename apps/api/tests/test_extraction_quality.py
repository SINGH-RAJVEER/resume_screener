from app.api.routes import csv_safe, resume_quality_payload
from app.persistence.models import ResumeVersion


def test_csv_cells_starting_with_formula_characters_are_neutralized() -> None:
	assert csv_safe("=SUM(A1)") == "'=SUM(A1)"
	assert csv_safe("+cmd") == "'+cmd"
	assert csv_safe("-2; --") == "'-2; --"
	assert csv_safe("@import") == "'@import"
	assert csv_safe("\tSUM(A1)") == "'\tSUM(A1)"
	assert csv_safe("\r=cmd") == "'\r=cmd"


def test_csv_plain_cells_pass_through_unchanged() -> None:
	assert csv_safe("Ada Lovelace") == "Ada Lovelace"
	assert csv_safe(85) == "85"
	assert csv_safe(None) == "None"


def test_resume_quality_payload_exposes_state_warnings_and_safe_metadata() -> None:
	version = ResumeVersion(
		id="version-1",
		resume_document_id="document-1",
		version=1,
		quality_state="review_required",
		extraction_blocks={
			"blocks": [{"id": "p1-b1", "text": "private resume text"}],
			"metadata": {
				"mediaType": "application/pdf",
				"pageCount": 2,
				"blockCount": 1,
				"characterCount": 120,
				"nonWhitespaceCharacterCount": 100,
			},
			"quality": {
				"state": "review_required",
				"warnings": ["1 of 2 pages contained no extractable text"],
			},
		},
		normalized_facts={
			"warnings": [
				"1 of 2 pages contained no extractable text",
				"Structured extraction was unavailable; only deterministic facts were used",
			]
		},
	)

	assert resume_quality_payload(version) == {
		"qualityState": "review_required",
		"qualityWarnings": [
			"1 of 2 pages contained no extractable text",
			"Structured extraction was unavailable; only deterministic facts were used",
		],
		"extractionMetadata": {
			"mediaType": "application/pdf",
			"pageCount": 2,
			"blockCount": 1,
			"characterCount": 120,
			"nonWhitespaceCharacterCount": 100,
		},
	}
	assert "private resume text" not in str(resume_quality_payload(version))
