from app.api.routes import resume_quality_payload
from app.persistence.models import ResumeVersion


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
