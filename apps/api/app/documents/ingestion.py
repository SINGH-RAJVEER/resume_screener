from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from zipfile import BadZipFile, ZipFile

MAX_RESUME_BYTES = 20 * 1024 * 1024
SUPPORTED_RESUME_TYPES = {
	"application/pdf": ".pdf",
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
	"text/plain": ".txt",
}


class DocumentValidationError(ValueError):
	pass


@dataclass(frozen=True)
class ValidatedResume:
	media_type: str
	extension: str


def validate_resume(
	content: bytes, media_type: str | None, filename: str | None
) -> ValidatedResume:
	if not content or len(content) > MAX_RESUME_BYTES:
		raise DocumentValidationError("Resume must be between 1 byte and 20 MB")
	if media_type not in SUPPORTED_RESUME_TYPES:
		raise DocumentValidationError("Resume must be a PDF, DOCX, or TXT file")
	extension = SUPPORTED_RESUME_TYPES[media_type]
	if not filename or PurePath(filename).suffix.casefold() != extension:
		raise DocumentValidationError("Resume filename does not match its media type")
	if media_type == "application/pdf" and not content.startswith(b"%PDF-"):
		raise DocumentValidationError("Resume content is not a PDF")
	if media_type.endswith("wordprocessingml.document"):
		validate_docx(content)
	return ValidatedResume(media_type=media_type, extension=extension)


def validate_docx(content: bytes) -> None:
	if not content.startswith(b"PK\x03\x04"):
		raise DocumentValidationError("Resume content is not a DOCX file")
	try:
		with ZipFile(BytesIO(content)) as archive:
			names = set(archive.namelist())
	except BadZipFile as error:
		raise DocumentValidationError("Resume DOCX file is malformed") from error
	if "[Content_Types].xml" not in names or "word/document.xml" not in names:
		raise DocumentValidationError("Resume content is not a DOCX file")
	if any(name.casefold().endswith("vbaproject.bin") for name in names):
		raise DocumentValidationError("Macro-enabled Office documents are not supported")
