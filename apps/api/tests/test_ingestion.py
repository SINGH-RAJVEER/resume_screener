from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.documents.ingestion import (
	DocumentValidationError,
	inspect_resume_zip,
	validate_document,
)


def test_accepts_digital_pdf_with_matching_name_and_media_type() -> None:
	validated = validate_document(b"%PDF-1.7\nresume", "application/pdf", "resume.pdf")

	assert validated.extension == ".pdf"


def test_rejects_pdf_with_an_invalid_signature() -> None:
	with pytest.raises(DocumentValidationError, match="not a PDF"):
		validate_document(b"not a PDF", "application/pdf", "resume.pdf")


def test_rejects_macro_enabled_docx_content() -> None:
	content = BytesIO()
	with ZipFile(content, "w") as archive:
		archive.writestr("[Content_Types].xml", "content types")
		archive.writestr("word/document.xml", "document")
		archive.writestr("word/vbaProject.bin", "macro")

	with pytest.raises(DocumentValidationError, match="Macro-enabled"):
		validate_document(
			content.getvalue(),
			"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
			"resume.docx",
		)


def test_rejects_docx_packages_with_suspicious_compression() -> None:
	content = BytesIO()
	with ZipFile(content, "w", compression=ZIP_DEFLATED) as archive:
		archive.writestr("[Content_Types].xml", "content types")
		archive.writestr("word/document.xml", "A" * 1_000_000)

	with pytest.raises(DocumentValidationError, match="suspicious compression ratio"):
		validate_document(
			content.getvalue(),
			"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
			"resume.docx",
		)


def test_rejects_docx_packages_with_too_many_entries() -> None:
	content = BytesIO()
	with ZipFile(content, "w") as archive:
		archive.writestr("[Content_Types].xml", "content types")
		archive.writestr("word/document.xml", "document")
		for index in range(1_001):
			archive.writestr(f"word/media/{index}.bin", b"x")

	with pytest.raises(DocumentValidationError, match="too many package entries"):
		validate_document(
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
		("readme.md", "Document must be a PDF, DOCX, or TXT file"),
	]


def test_rejects_windows_paths_and_excessive_zip_nesting() -> None:
	content = BytesIO()
	with ZipFile(content, "w") as archive:
		archive.writestr("C:\\resumes\\candidate.txt", "invalid")
		archive.writestr("/".join(["nested"] * 11) + "/candidate.txt", "invalid")

	entries = inspect_resume_zip(content.getvalue())

	assert [(entry.name, entry.reason) for entry in entries] == [
		("C:\\resumes\\candidate.txt", "ZIP entry has an unsafe path"),
		(
			"/".join(["nested"] * 11) + "/candidate.txt",
			"ZIP entry exceeds the nesting limit",
		),
	]
