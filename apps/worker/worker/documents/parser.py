import re
import unicodedata
from collections import Counter
from io import BytesIO
from typing import Literal, TypedDict
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf import filters as pdf_filters

MAX_PAGES = 100
MAX_PDF_PAGE_DIMENSION_POINTS = 14_400
MAX_PDF_DECOMPRESSED_STREAM_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 250_000
MIN_RELIABLE_NON_WHITESPACE_CHARACTERS = 40
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
INSTRUCTION_LIKE_TEXT = re.compile(
	r"\b(?:ignore (?:all |any )?(?:previous|prior) instructions|"
	r"reveal (?:the )?system prompt|give this resume (?:a )?perfect score)\b",
	re.IGNORECASE,
)

pdf_filters.ZLIB_MAX_OUTPUT_LENGTH = MAX_PDF_DECOMPRESSED_STREAM_BYTES


class DocumentParseError(ValueError):
	pass


class EvidenceBlock(TypedDict):
	id: str
	page: int
	readingOrder: int
	text: str
	method: Literal["plain_text", "pdf_text", "docx_xml"]
	bbox: list[float] | None


class ExtractionMetadata(TypedDict):
	mediaType: str
	pageCount: int
	blockCount: int
	characterCount: int
	nonWhitespaceCharacterCount: int


class ExtractionQuality(TypedDict):
	state: Literal["ready", "review_required"]
	warnings: list[str]


class ParsedDocument(TypedDict):
	blocks: list[EvidenceBlock]
	metadata: ExtractionMetadata
	quality: ExtractionQuality


def extract_blocks(content: bytes, media_type: str) -> ParsedDocument:
	if media_type == "text/plain":
		text = decode_text(content)
		return parsed_document(
			paragraph_blocks([text], "plain_text"),
			media_type=media_type,
			page_count=1,
		)
	if media_type == "application/pdf":
		return extract_pdf_blocks(content)
	if media_type.endswith("wordprocessingml.document"):
		paragraphs = extract_docx_paragraphs(content)
		return parsed_document(
			paragraph_blocks(paragraphs, "docx_xml", split_paragraphs=False),
			media_type=media_type,
			page_count=1,
		)
	raise DocumentParseError("Unsupported resume document type")


def extract_pdf_blocks(content: bytes) -> ParsedDocument:
	try:
		reader = PdfReader(BytesIO(content), strict=True)
	except Exception as error:
		raise DocumentParseError("Resume PDF could not be parsed") from error
	if reader.is_encrypted:
		raise DocumentParseError("Encrypted resume PDFs are not supported")
	if len(reader.pages) > MAX_PAGES:
		raise DocumentParseError("Resume PDF exceeds 100 pages")
	for page in reader.pages:
		width = float(page.mediabox.width)
		height = float(page.mediabox.height)
		if (
			width <= 0
			or height <= 0
			or width > MAX_PDF_PAGE_DIMENSION_POINTS
			or height > MAX_PDF_PAGE_DIMENSION_POINTS
		):
			raise DocumentParseError("Resume PDF has unsupported page dimensions")
	page_text: list[str] = []
	try:
		for page in reader.pages:
			page_text.append(normalize_text(page.extract_text() or "", allow_empty=True))
	except Exception as error:
		raise DocumentParseError("Resume PDF text could not be extracted") from error
	if not any(item.strip() for item in page_text):
		raise DocumentParseError("Scanned or image-only resume PDFs are not supported")
	blocks = paragraph_blocks(page_text, "pdf_text")
	return parsed_document(
		blocks,
		media_type="application/pdf",
		page_count=len(page_text),
		empty_page_count=sum(not item.strip() for item in page_text),
	)


def extract_docx_paragraphs(content: bytes) -> list[str]:
	try:
		with ZipFile(BytesIO(content)) as archive:
			document = archive.read("word/document.xml")
	except (BadZipFile, KeyError) as error:
		raise DocumentParseError("Resume DOCX could not be parsed") from error
	try:
		root = ElementTree.fromstring(document)
	except ElementTree.ParseError as error:
		raise DocumentParseError("Resume DOCX could not be parsed") from error
	paragraphs = [
		normalize_text(paragraph_text(paragraph), allow_empty=True)
		for paragraph in root.findall(f".//{{{WORD_NAMESPACE}}}p")
	]
	paragraphs = [paragraph for paragraph in paragraphs if paragraph.strip()]
	if not paragraphs:
		raise DocumentParseError("Resume DOCX contains no extractable text")
	return paragraphs


def paragraph_text(paragraph: ElementTree.Element[str]) -> str:
	parts: list[str] = []
	for node in paragraph.iter():
		if node.tag == f"{{{WORD_NAMESPACE}}}t":
			parts.append(node.text or "")
		elif node.tag == f"{{{WORD_NAMESPACE}}}tab":
			parts.append("\t")
		elif node.tag in {f"{{{WORD_NAMESPACE}}}br", f"{{{WORD_NAMESPACE}}}cr"}:
			parts.append("\n")
	return "".join(parts)


def decode_text(content: bytes) -> str:
	encoding = "utf-16" if content.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
	try:
		text = content.decode(encoding)
	except UnicodeDecodeError as error:
		raise DocumentParseError("Resume text encoding is not supported") from error
	return normalize_text(text)


def normalize_text(text: str, *, allow_empty: bool = False) -> str:
	normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
	if any(ord(character) < 32 and character not in {"\n", "\t"} for character in normalized):
		raise DocumentParseError("Resume text contains unsupported control characters")
	if not allow_empty and not normalized.strip():
		raise DocumentParseError("Resume text contains no extractable text")
	if len(normalized) > MAX_EXTRACTED_CHARACTERS:
		raise DocumentParseError("Resume contains too much extractable text")
	return normalized


def paragraph_blocks(
	pages: list[str],
	method: Literal["plain_text", "pdf_text", "docx_xml"],
	*,
	split_paragraphs: bool = True,
) -> list[EvidenceBlock]:
	blocks: list[EvidenceBlock] = []
	reading_order = 1
	for page_number, page_text_value in enumerate(pages, start=1):
		paragraphs = (
			re.split(r"\n[\t ]*\n+", page_text_value)
			if split_paragraphs
			else [page_text_value]
		)
		page_block_number = 1
		for paragraph in paragraphs:
			text = paragraph.strip()
			if not text:
				continue
			blocks.append(
				{
					"id": f"p{page_number}-b{page_block_number}",
					"page": page_number,
					"readingOrder": reading_order,
					"text": text,
					"method": method,
					"bbox": None,
				}
			)
			page_block_number += 1
			reading_order += 1
	return blocks


def parsed_document(
	blocks: list[EvidenceBlock],
	*,
	media_type: str,
	page_count: int,
	empty_page_count: int = 0,
) -> ParsedDocument:
	joined_text = "\n\n".join(block["text"] for block in blocks)
	if not joined_text.strip():
		raise DocumentParseError("Resume contains no extractable text")
	if len(joined_text) > MAX_EXTRACTED_CHARACTERS:
		raise DocumentParseError("Resume contains too much extractable text")
	non_whitespace_count = sum(not character.isspace() for character in joined_text)
	warnings: list[str] = []
	if non_whitespace_count < MIN_RELIABLE_NON_WHITESPACE_CHARACTERS:
		warnings.append("Document contains very little extractable text")
	if empty_page_count:
		label = "page" if page_count == 1 else "pages"
		warnings.append(
			f"{empty_page_count} of {page_count} {label} contained no extractable text"
		)
	if duplicate_block_ratio(blocks) >= 0.5:
		warnings.append("Extracted text contains repeated blocks that may be duplicated")
	if joined_text.count("\ufffd") / max(len(joined_text), 1) >= 0.01:
		warnings.append("Extracted text contains many unreadable characters")
	if INSTRUCTION_LIKE_TEXT.search(joined_text):
		warnings.append("Document contains instruction-like text that requires review")
	return {
		"blocks": blocks,
		"metadata": {
			"mediaType": media_type,
			"pageCount": page_count,
			"blockCount": len(blocks),
			"characterCount": len(joined_text),
			"nonWhitespaceCharacterCount": non_whitespace_count,
		},
		"quality": {
			"state": "review_required" if warnings else "ready",
			"warnings": warnings,
		},
	}


def duplicate_block_ratio(blocks: list[EvidenceBlock]) -> float:
	if len(blocks) < 2:
		return 0
	normalized = [re.sub(r"\s+", " ", block["text"]).strip().casefold() for block in blocks]
	counts = Counter(normalized)
	duplicate_count = sum(count - 1 for count in counts.values())
	return duplicate_count / len(blocks)
