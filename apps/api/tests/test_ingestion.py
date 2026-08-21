from io import BytesIO
from zipfile import ZipFile

import pytest

from app.documents.ingestion import (
	DocumentValidationError,
	inspect_resume_zip,
	validate_resume,
)


def test_accepts_digital_pdf_with_matching_name_and_media_type() -> None:
	validated = validate_resume(b"%PDF-1.7\nresume", "application/pdf", "resume.pdf")

	assert validated.extension == ".pdf"


def test_rejects_pdf_with_an_invalid_signature() -> None:
	with pytest.raises(DocumentValidationError, match="not a PDF"):
		validate_resume(b"not a PDF", "application/pdf", "resume.pdf")


def test_rejects_macro_enabled_docx_content() -> None:
	content = BytesIO()
	with ZipFile(content, "w") as archive:
		archive.writestr("[Content_Types].xml", "content types")
		archive.writestr("word/document.xml", "document")
		archive.writestr("word/vbaProject.bin", "macro")

	with pytest.raises(DocumentValidationError, match="Macro-enabled"):
		validate_resume(
			content.getvalue(),
			"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
			"resume.docx",
		)


def test_reports_each_invalid_zip_entry_without_rejecting_valid_resumes() -> None:
	content = BytesIO()
	with ZipFile(content, "w") as archive:
		archive.writestr("valid.txt", "Python engineer")
		archive.writestr("unsafe/../resume.txt", "invalid")
		archive.writestr("readme.md", "invalid")

	entries = inspect_resume_zip(content.getvalue())

	assert [(entry.name, entry.reason) for entry in entries] == [
		("valid.txt", None),
		("unsafe/../resume.txt", "ZIP entry has an unsafe path"),
		("readme.md", "Resume must be a PDF, DOCX, or TXT file"),
	]
