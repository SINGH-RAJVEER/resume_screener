import re
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath, PurePosixPath
from stat import S_IFLNK, S_IFMT
from zipfile import BadZipFile, ZipFile

MAX_RESUME_BYTES = 20 * 1024 * 1024
MAX_BATCH_FILES = 500
MAX_BATCH_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_ZIP_DEPTH = 10
MAX_DOCX_ENTRIES = 1_000
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
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


@dataclass(frozen=True)
class BatchEntry:
	name: str
	content: bytes | None
	reason: str | None


def validate_document(
	content: bytes, media_type: str | None, filename: str | None
) -> ValidatedResume:
	if not content or len(content) > MAX_RESUME_BYTES:
		raise DocumentValidationError("Document must be between 1 byte and 20 MB")
	if media_type not in SUPPORTED_RESUME_TYPES:
		raise DocumentValidationError("Document must be a PDF, DOCX, or TXT file")
	extension = SUPPORTED_RESUME_TYPES[media_type]
	if not filename or PurePath(filename).suffix.casefold() != extension:
		raise DocumentValidationError("Document filename does not match its media type")
	if media_type == "application/pdf" and not content.startswith(b"%PDF-"):
		raise DocumentValidationError("Document content is not a PDF")
	if media_type.endswith("wordprocessingml.document"):
		validate_docx(content)
	return ValidatedResume(media_type=media_type, extension=extension)


def validate_docx(content: bytes) -> None:
	if not content.startswith(b"PK\x03\x04"):
		raise DocumentValidationError("Document content is not a DOCX file")
	try:
		with ZipFile(BytesIO(content)) as archive:
			entries = archive.infolist()
	except BadZipFile as error:
		raise DocumentValidationError("Document DOCX file is malformed") from error
	if len(entries) > MAX_DOCX_ENTRIES:
		raise DocumentValidationError("Document DOCX has too many package entries")
	if sum(entry.file_size for entry in entries) > MAX_DOCX_UNCOMPRESSED_BYTES:
		raise DocumentValidationError("Document DOCX package is too large")
	if any(entry.flag_bits & 0x1 for entry in entries):
		raise DocumentValidationError("Encrypted DOCX packages are not supported")
	if any(
		entry.compress_size
		and entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO
		for entry in entries
	):
		raise DocumentValidationError("Document DOCX has a suspicious compression ratio")
	names = {entry.filename for entry in entries}
	if "[Content_Types].xml" not in names or "word/document.xml" not in names:
		raise DocumentValidationError("Document content is not a DOCX file")
	if any(name.casefold().endswith("vbaproject.bin") for name in names):
		raise DocumentValidationError("Macro-enabled Office documents are not supported")


def unsafe_path(filename: str) -> bool:
	path = PurePosixPath(filename.replace("\\", "/"))
	return (
		path.is_absolute()
		or ".." in path.parts
		or re.match(r"^[A-Za-z]:", filename) is not None
	)


def inspect_resume_files(files: Sequence[tuple[str | None, bytes]]) -> list[BatchEntry]:
	"""Validate loose uploads individually so one bad file never fails the batch."""
	if not files:
		raise DocumentValidationError("Resume batch must contain at least one file")
	if len(files) > MAX_BATCH_FILES:
		raise DocumentValidationError("Resume batch exceeds 500 files")
	if sum(len(content) for _, content in files) > MAX_BATCH_UNCOMPRESSED_BYTES:
		raise DocumentValidationError("Resume batch exceeds 500 MB")
	result: list[BatchEntry] = []
	for filename, content in files:
		name = filename or ""
		reason = file_entry_reason(name, content)
		result.append(BatchEntry(name, None if reason else content, reason))
	return result


def file_entry_reason(filename: str, content: bytes) -> str | None:
	if unsafe_path(filename):
		return "Resume file has an unsafe path"
	if len(PurePosixPath(filename.replace("\\", "/")).parts) > MAX_ZIP_DEPTH + 1:
		return "Resume file exceeds the nesting limit"
	media_type = media_type_for_name(filename)
	if media_type is None:
		return "Document must be a PDF, DOCX, or TXT file"
	try:
		validate_document(content, media_type, filename)
	except DocumentValidationError as error:
		return str(error)
	return None


def inspect_resume_zip(content: bytes) -> list[BatchEntry]:
	try:
		archive = ZipFile(BytesIO(content))
	except BadZipFile as error:
		raise DocumentValidationError("Resume ZIP file is malformed") from error
	with archive:
		entries = [entry for entry in archive.infolist() if not entry.is_dir()]
		if len(entries) > MAX_BATCH_FILES:
			raise DocumentValidationError("Resume ZIP exceeds 500 files")
		if sum(entry.file_size for entry in entries) > MAX_BATCH_UNCOMPRESSED_BYTES:
			raise DocumentValidationError("Resume ZIP exceeds 500 MB uncompressed")
		result: list[BatchEntry] = []
		for entry in entries:
			reason = zip_entry_reason(
				entry.filename,
				entry.external_attr,
				entry.flag_bits,
				entry.compress_size,
				entry.file_size,
			)
			if reason:
				result.append(BatchEntry(entry.filename, None, reason))
				continue
			try:
				entry_content = archive.read(entry)
			except (BadZipFile, RuntimeError, NotImplementedError):
				result.append(BatchEntry(entry.filename, None, "ZIP entry could not be read"))
				continue
			try:
				validate_document(
					entry_content, media_type_for_name(entry.filename), entry.filename
				)
			except DocumentValidationError as error:
				result.append(BatchEntry(entry.filename, None, str(error)))
			else:
				result.append(BatchEntry(entry.filename, entry_content, None))
		return result


def zip_entry_reason(
	filename: str,
	external_attr: int,
	flag_bits: int,
	compressed_size: int,
	file_size: int,
) -> str | None:
	path = PurePosixPath(filename.replace("\\", "/"))
	if unsafe_path(filename):
		return "ZIP entry has an unsafe path"
	if len(path.parts) - 1 > MAX_ZIP_DEPTH:
		return "ZIP entry exceeds the nesting limit"
	if S_IFMT(external_attr >> 16) == S_IFLNK:
		return "ZIP entry is a symlink"
	if flag_bits & 0x1:
		return "Encrypted ZIP entries are not supported"
	if filename.casefold().endswith(".zip"):
		return "Nested ZIP archives are not supported"
	if not compressed_size and file_size:
		return "ZIP entry has a suspicious compression ratio"
	if compressed_size and file_size / compressed_size > MAX_COMPRESSION_RATIO:
		return "ZIP entry has a suspicious compression ratio"
	return None


def media_type_for_name(filename: str) -> str | None:
	extension = PurePath(filename).suffix.casefold()
	return {extension: media_type for media_type, extension in SUPPORTED_RESUME_TYPES.items()}.get(
		extension
	)
