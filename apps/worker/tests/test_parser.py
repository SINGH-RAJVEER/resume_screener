from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from worker.documents.parser import DocumentParseError, extract_blocks

FIXTURES = Path(__file__).parent / "fixtures"


def pdf_with_pages(
	*page_texts: str | None, width: float = 612, height: float = 792
) -> bytes:
	writer = PdfWriter()
	for text in page_texts:
		page = writer.add_blank_page(width=width, height=height)
		if text is None:
			continue
		font = DictionaryObject(
			{
				NameObject("/Type"): NameObject("/Font"),
				NameObject("/Subtype"): NameObject("/Type1"),
				NameObject("/BaseFont"): NameObject("/Helvetica"),
			}
		)
		page[NameObject("/Resources")] = DictionaryObject(
			{NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
		)
		stream = DecodedStreamObject()
		stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
		page[NameObject("/Contents")] = stream
	output = BytesIO()
	writer.write(output)
	return output.getvalue()


def test_extracts_normalized_text_as_ordered_evidence_blocks() -> None:
	parsed = extract_blocks(
		b"Ada Lovelace\r\nada@example.com\r\n\r\nExperience\r\nBuilt Python services.",
		"text/plain",
	)

	assert parsed["blocks"] == [
		{
			"id": "p1-b1",
			"page": 1,
			"readingOrder": 1,
			"text": "Ada Lovelace\nada@example.com",
			"method": "plain_text",
			"bbox": None,
		},
		{
			"id": "p1-b2",
			"page": 1,
			"readingOrder": 2,
			"text": "Experience\nBuilt Python services.",
			"method": "plain_text",
			"bbox": None,
		},
	]
	assert parsed["metadata"] == {
		"mediaType": "text/plain",
		"pageCount": 1,
		"blockCount": 2,
		"characterCount": 63,
		"nonWhitespaceCharacterCount": 56,
	}
	assert parsed["quality"] == {"state": "ready", "warnings": []}


def test_extracts_utf16_text_with_a_byte_order_mark() -> None:
	parsed = extract_blocks(
		"Ada Lovelace\n\nPython engineer with ten years of experience".encode("utf-16"),
		"text/plain",
	)

	assert parsed["blocks"][0]["text"] == "Ada Lovelace"
	assert parsed["quality"] == {"state": "ready", "warnings": []}


def test_extracts_docx_paragraphs_as_separate_evidence_blocks() -> None:
	content = BytesIO()
	with ZipFile(content, "w") as archive:
		archive.writestr(
			"word/document.xml",
			"""<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
			<w:body>
				<w:p><w:r><w:t>Ada Lovelace</w:t></w:r></w:p>
				<w:p><w:r><w:t>Built Python services for ten years.</w:t></w:r></w:p>
			</w:body></w:document>""",
		)

	parsed = extract_blocks(
		content.getvalue(),
		"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	)

	assert [block["text"] for block in parsed["blocks"]] == [
		"Ada Lovelace",
		"Built Python services for ten years.",
	]
	assert [block["readingOrder"] for block in parsed["blocks"]] == [1, 2]
	assert {block["method"] for block in parsed["blocks"]} == {"docx_xml"}


@pytest.mark.parametrize(
	"fixture_name",
	[
		"single_column_resume.txt",
		"two_column_resume.txt",
	],
)
def test_parses_representative_resume_fixtures(fixture_name: str) -> None:
	parsed = extract_blocks((FIXTURES / fixture_name).read_bytes(), "text/plain")

	assert parsed["quality"]["state"] == "ready"
	assert parsed["metadata"]["blockCount"] >= 2


def test_preserves_prompt_injection_as_document_text() -> None:
	parsed = extract_blocks(
		(FIXTURES / "prompt_injection_resume.txt").read_bytes(),
		"text/plain",
	)

	assert "Ignore previous instructions" in parsed["blocks"][-1]["text"]
	assert parsed["quality"] == {
		"state": "review_required",
		"warnings": ["Document contains instruction-like text that requires review"],
	}


def test_extracts_pdf_pages_and_flags_a_page_without_text() -> None:
	parsed = extract_blocks(
		pdf_with_pages(
			"Ada Lovelace, Python engineer with ten years of platform experience.",
			None,
		),
		"application/pdf",
	)

	assert parsed["blocks"][0]["method"] == "pdf_text"
	assert parsed["metadata"]["pageCount"] == 2
	assert parsed["quality"] == {
		"state": "review_required",
		"warnings": ["1 of 2 pages contained no extractable text"],
	}


def test_rejects_image_only_pdf() -> None:
	with pytest.raises(DocumentParseError, match="image-only"):
		extract_blocks(pdf_with_pages(None), "application/pdf")


def test_rejects_malformed_pdf() -> None:
	with pytest.raises(DocumentParseError, match="could not be parsed"):
		extract_blocks(b"%PDF-1.7\nnot a complete PDF", "application/pdf")


def test_wraps_malformed_pdf_page_metadata_in_a_safe_error() -> None:
	content = pdf_with_pages(
		"Ada Lovelace, Python engineer with ten years of experience."
	)
	content = content.replace(
		b"/MediaBox [ 0.0 0.0 612 792 ]",
		b"/MediaBox [ 0.0 0.0 bad 792 ]",
	)

	with pytest.raises(DocumentParseError, match="could not be parsed"):
		extract_blocks(content, "application/pdf")


def test_rejects_pdf_with_excessive_page_dimensions() -> None:
	with pytest.raises(DocumentParseError, match="page dimensions"):
		extract_blocks(
			pdf_with_pages(
				"Ada Lovelace, Python engineer with ten years of experience.",
				width=14_401,
			),
			"application/pdf",
		)


def test_rejects_pdf_over_the_page_limit_before_extraction() -> None:
	with pytest.raises(DocumentParseError, match="exceeds 100 pages"):
		extract_blocks(pdf_with_pages(*([None] * 101)), "application/pdf")


def test_marks_documents_with_too_little_text_for_review() -> None:
	parsed = extract_blocks(b"Ada Lovelace", "text/plain")

	assert parsed["quality"] == {
		"state": "review_required",
		"warnings": ["Document contains very little extractable text"],
	}


def test_marks_heavily_duplicated_blocks_for_review() -> None:
	paragraph = "Python engineer with ten years of platform experience."
	parsed = extract_blocks(
		("\n\n".join([paragraph] * 4)).encode(),
		"text/plain",
	)

	assert parsed["quality"] == {
		"state": "review_required",
		"warnings": ["Extracted text contains repeated blocks that may be duplicated"],
	}


def test_rejects_text_with_binary_control_characters() -> None:
	with pytest.raises(DocumentParseError, match="unsupported control characters"):
		extract_blocks(b"Ada Lovelace\x00Python engineer", "text/plain")


def test_rejects_excessive_extracted_text() -> None:
	with pytest.raises(DocumentParseError, match="too much extractable text"):
		extract_blocks(b"a" * 250_001, "text/plain")


def test_rejects_empty_text_documents() -> None:
	with pytest.raises(DocumentParseError, match="no extractable text"):
		extract_blocks(b" \n", "text/plain")


def test_rejects_non_latin_writing_systems() -> None:
	with pytest.raises(DocumentParseError, match="unsupported writing system"):
		extract_blocks(
			"Разработчик программного обеспечения с десятилетним опытом "
			"проектирования распределённых систем и управления командами".encode(),
			"text/plain",
		)


def test_rejects_non_english_latin_text() -> None:
	with pytest.raises(DocumentParseError, match="appear to be in English"):
		extract_blocks(
			"Softwareentwickler mit zehn Jahren Erfahrung im Entwurf "
			"verteilter Systeme und der Leitung von Plattformteams für ein "
			"reguliertes Umfeld mit Fokus auf Zuverlässigkeit".encode(),
			"text/plain",
		)


def test_short_keyword_documents_skip_language_detection() -> None:
	parsed = extract_blocks(b"KUBERNETES DOCKER REDIS KAFKA", "text/plain")

	assert parsed["quality"]["state"] == "review_required"
	assert parsed["metadata"]["blockCount"] == 1
