import re
import unicodedata
from collections import Counter
from io import BytesIO
from statistics import median
from typing import Literal, NamedTuple, TypedDict, cast
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf import filters as pdf_filters

MAX_PAGES = 100
MAX_PDF_PAGE_DIMENSION_POINTS = 14_400
MAX_PDF_DECOMPRESSED_STREAM_BYTES = 25 * 1024 * 1024
# A small DOCX can decompress to gigabytes of XML; bound the uncompressed
# body the same way the PDF stream cap bounds inflated content streams.
MAX_DOCX_DOCUMENT_XML_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 250_000
MIN_RELIABLE_NON_WHITESPACE_CHARACTERS = 40
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
# PDF geometry heuristics. Coordinates keep the PDF coordinate system, where
# the origin is the bottom-left corner of the page.
PDF_LINE_TOLERANCE_POINTS = 3.0
PDF_CLUSTER_GAP_POINTS = 100.0
PDF_BLOCK_MERGE_FACTOR = 1.8
PDF_CHAR_WIDTH_FACTOR = 0.55
INSTRUCTION_LIKE_TEXT = re.compile(
	r"\b(?:ignore (?:all |any )?(?:previous|prior) instructions|"
	r"reveal (?:the )?system prompt|give this resume (?:a )?perfect score)\b",
	re.IGNORECASE,
)
# The product supports English only. Detection is a conservative heuristic:
# non-Latin scripts reject on script share, and longer Latin documents must
# contain at least one recognized English function or resume word. Pure
# keyword documents below the token threshold are never rejected.
NON_LATIN_SCRIPT_SHARE = 0.25
MIN_LANGUAGE_TOKENS = 15
ENGLISH_WORDS = frozenset(
	"""
	the and for with from to of on at by an is are was were be been as it its
	this that these those or but not have has had will would can could their
	our your they we you
	experience senior junior engineer engineering manager management developed
	developer development built designed led managed operated created improved
	reduced increased implemented delivered maintained supported education
	university college degree bachelor master science computer software
	services service platform systems system team teams project projects
	skills certified certification location united kingdom states corporation
	corp inc ltd llc group company consultant analyst specialist coordinator
	director head lead staff principal architect
	""".split()
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


class PdfFragment(NamedTuple):
	text: str
	x: float
	y: float
	size: float


def extract_pdf_blocks(content: bytes) -> ParsedDocument:
	try:
		reader = PdfReader(BytesIO(content), strict=True)
		if reader.is_encrypted:
			raise DocumentParseError("Encrypted resume PDFs are not supported")
		pages = list(reader.pages)
		if len(pages) > MAX_PAGES:
			raise DocumentParseError("Resume PDF exceeds 100 pages")
		for page in pages:
			width = float(page.mediabox.width)
			height = float(page.mediabox.height)
			if (
				width <= 0
				or height <= 0
				or width > MAX_PDF_PAGE_DIMENSION_POINTS
				or height > MAX_PDF_PAGE_DIMENSION_POINTS
			):
				raise DocumentParseError("Resume PDF has unsupported page dimensions")
	except DocumentParseError:
		raise
	except Exception as error:
		raise DocumentParseError("Resume PDF could not be parsed") from error
	blocks: list[EvidenceBlock] = []
	empty_page_count = 0
	try:
		for page_number, page in enumerate(pages, start=1):
			fragments = pdf_page_fragments(page)
			fallback_text = ""
			if not fragments:
				fallback_text = normalize_text(
					str(page.extract_text() or ""), allow_empty=True
				).strip()
			if not fragments and not fallback_text:
				empty_page_count += 1
				continue
			page_blocks = pdf_page_blocks(fragments, fallback_text, page_number, len(blocks))
			blocks.extend(page_blocks)
			if not page_blocks:
				empty_page_count += 1
	except DocumentParseError:
		raise
	except Exception as error:
		raise DocumentParseError("Resume PDF text could not be extracted") from error
	if not blocks:
		raise DocumentParseError("Scanned or image-only resume PDFs are not supported")
	return parsed_document(
		blocks,
		media_type="application/pdf",
		page_count=len(pages),
		empty_page_count=empty_page_count,
	)


def pdf_page_fragments(page: object) -> list[PdfFragment]:
	fragments: list[PdfFragment] = []
	font_size = 12.0

	def visitor_before(operator: object, operands: object, cm: object, tm: object) -> None:
		nonlocal font_size
		# visitor_text receives memoized positions that reset at every BT;
		# the operand hook reports the live text matrix for each show-text
		# operator instead.
		if operator == b"Tf":
			settings = cast(list[object], operands)
			if len(settings) > 1 and isinstance(settings[1], (int, float)):
				font_size = float(settings[1])
			return
		if operator not in (b"Tj", b"TJ", b"'", b'"'):
			return
		text = shown_text(cast(list[object], operands))
		if not text.strip():
			return
		matrix = cast(list[object], tm)
		fragments.append(
			PdfFragment(text.strip(), float(matrix[4]), float(matrix[5]), font_size)
		)

	cast("PdfPage", page).extract_text(visitor_operand_before=visitor_before)
	return fragments


def shown_text(operands: list[object]) -> str:
	parts: list[str] = []
	for operand in operands:
		if isinstance(operand, bytes):
			parts.append(decode_pdf_string(operand))
		elif isinstance(operand, str):
			parts.append(operand)
		elif isinstance(operand, list):
			for entry in cast(list[object], operand):
				if isinstance(entry, bytes):
					parts.append(decode_pdf_string(entry))
				elif isinstance(entry, str):
					parts.append(entry)
	return "".join(parts)


def decode_pdf_string(value: bytes) -> str:
	# Show-text operands reach the visitor as raw bytes on current pypdf
	# releases. UTF-16BE literals carry a BOM; unmarked literals use
	# PDFDocEncoding, whose ASCII range matches latin-1.
	if value.startswith(b"\xfe\xff"):
		return value.decode("utf-16-be", errors="replace")
	return value.decode("latin-1")


def fragment_width(fragment: PdfFragment) -> float:
	return len(fragment.text) * fragment.size * PDF_CHAR_WIDTH_FACTOR


def group_pdf_lines(fragments: list[PdfFragment]) -> list[list[PdfFragment]]:
	ordered = sorted(fragments, key=lambda fragment: (-fragment.y, fragment.x))
	lines: list[list[PdfFragment]] = []
	for fragment in ordered:
		if lines and abs(lines[-1][0].y - fragment.y) <= PDF_LINE_TOLERANCE_POINTS:
			lines[-1].append(fragment)
		else:
			lines.append([fragment])
	for line in lines:
		line.sort(key=lambda fragment: fragment.x)
	return lines


def column_boundaries_for(fragments: list[PdfFragment]) -> list[float]:
	if len(fragments) < 4:
		return []
	ordered = sorted(fragments, key=lambda fragment: fragment.x)
	clusters: list[list[PdfFragment]] = [[ordered[0]]]
	for fragment in ordered[1:]:
		if fragment.x - clusters[-1][-1].x > PDF_CLUSTER_GAP_POINTS:
			clusters.append([fragment])
		else:
			clusters[-1].append(fragment)
	# A region holding a single fragment cannot anchor a layout boundary.
	if len(clusters) < 2 or any(len(cluster) < 2 for cluster in clusters):
		return []
	return [
		(clusters[index][-1].x + clusters[index + 1][0].x) / 2
		for index in range(len(clusters) - 1)
	]


def ordered_pdf_lines(
	lines: list[list[PdfFragment]],
) -> list[tuple[int, list[PdfFragment]]]:
	fragments = [fragment for line in lines for fragment in line]
	boundaries = column_boundaries_for(fragments)
	row_major = [(0, line) for line in sorted(lines, key=lambda line: -line[0].y)]
	# Two or more aligned regions across the page indicate a table; keep
	# visual row order. One boundary indicates columns or a sidebar.
	if len(boundaries) != 1:
		return row_major
	boundary = boundaries[0]

	def column_of(x: float) -> int:
		return 1 if x > boundary else 0

	ordered: list[tuple[int, list[PdfFragment]]] = []
	for line in lines:
		run: list[PdfFragment] = [line[0]]
		for fragment in line[1:]:
			if column_of(fragment.x) != column_of(run[0].x):
				ordered.append((column_of(run[0].x), run))
				run = [fragment]
			else:
				run.append(fragment)
		ordered.append((column_of(run[0].x), run))
	ordered.sort(key=lambda item: (item[0], -item[1][0].y))
	return ordered


def pdf_page_blocks(
	fragments: list[PdfFragment],
	fallback_text: str,
	page_number: int,
	previous_block_count: int,
) -> list[EvidenceBlock]:
	if not fragments:
		return [
			evidence_block(
				page_number,
				previous_block_count + 1,
				fallback_text,
				"pdf_text",
				None,
			)
		]
	lines = group_pdf_lines(fragments)
	ordered = ordered_pdf_lines(lines)
	# Expected leading follows the median font size; observed gaps cannot
	# reveal a section break when a page has too few lines.
	font_sizes = [fragment.size for line in lines for fragment in line]
	merge_gap = median(font_sizes) * PDF_BLOCK_MERGE_FACTOR if font_sizes else None
	blocks: list[EvidenceBlock] = []
	line_texts: list[str] = []
	bbox: list[float] | None = None
	previous_column: int | None = None
	previous_y: float | None = None

	def flush() -> None:
		nonlocal line_texts, bbox
		text = normalize_text("\n".join(line_texts), allow_empty=True).strip()
		if text:
			blocks.append(
				evidence_block(
					page_number,
					previous_block_count + len(blocks) + 1,
					text,
					"pdf_text",
					bbox,
				)
			)
		line_texts = []
		bbox = None

	for column, segment in ordered:
		started_new_block = previous_column is not None and (
			column != previous_column
			or (
				merge_gap is not None
				and previous_y is not None
				and previous_y - segment[0].y > merge_gap
			)
		)
		if started_new_block:
			flush()
		line_texts.append(" ".join(fragment.text for fragment in segment))
		segment_bbox = [
			min(fragment.x for fragment in segment),
			min(fragment.y for fragment in segment) - segment[0].size,
			max(fragment.x + fragment_width(fragment) for fragment in segment),
			max(fragment.y for fragment in segment) + segment[0].size,
		]
		bbox = (
			segment_bbox
			if bbox is None
			else [
				min(bbox[0], segment_bbox[0]),
				min(bbox[1], segment_bbox[1]),
				max(bbox[2], segment_bbox[2]),
				max(bbox[3], segment_bbox[3]),
			]
		)
		previous_column = column
		previous_y = segment[0].y
	flush()
	return blocks


def extract_docx_paragraphs(content: bytes) -> list[str]:
	try:
		with ZipFile(BytesIO(content)) as archive:
			# Read only the main document part. Encrypted archives raise
			# RuntimeError and unsupported compression raises
			# NotImplementedError; both are malformed input here.
			info = archive.getinfo("word/document.xml")
			if info.file_size > MAX_DOCX_DOCUMENT_XML_BYTES:
				raise DocumentParseError("Resume DOCX decompresses to too much content")
			document = archive.read("word/document.xml")
	except DocumentParseError:
		raise
	except (BadZipFile, KeyError, NotImplementedError, RuntimeError) as error:
		raise DocumentParseError("Resume DOCX could not be parsed") from error
	if b"<!DOCTYPE" in document or b"<!ENTITY" in document:
		# WordprocessingML never carries a DTD; entity declarations are the
		# billion-laughs expansion vector, so reject them before parsing.
		raise DocumentParseError("Resume DOCX contains unsupported markup declarations")
	try:
		root = ElementTree.fromstring(document)
	except (ElementTree.ParseError, ValueError) as error:
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


def evidence_block(
	page: int,
	reading_order: int,
	text: str,
	method: Literal["plain_text", "pdf_text", "docx_xml"],
	bbox: list[float] | None,
) -> EvidenceBlock:
	return {
		"id": f"p{page}-b{reading_order}",
		"page": page,
		"readingOrder": reading_order,
		"text": text,
		"method": method,
		"bbox": bbox,
	}


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
		for paragraph in paragraphs:
			text = paragraph.strip()
			if not text:
				continue
			blocks.append(evidence_block(page_number, reading_order, text, method, None))
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
	reject_non_english_text(joined_text)
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


def reject_non_english_text(text: str) -> None:
	letters = [character for character in text if character.isalpha()]
	if letters:
		non_latin = sum(1 for character in letters if ord(character) > 0x24F)
		if non_latin / len(letters) > NON_LATIN_SCRIPT_SHARE:
			raise DocumentParseError("Resume text uses an unsupported writing system")
	tokens = re.findall(r"[A-Za-z]{2,}", text)
	if len(tokens) >= MIN_LANGUAGE_TOKENS and not any(
		token.casefold() in ENGLISH_WORDS for token in tokens
	):
		raise DocumentParseError("Resume text does not appear to be in English")
