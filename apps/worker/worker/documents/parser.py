
from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader

MAX_PAGES = 100


class DocumentParseError(ValueError):
	pass


def extract_blocks(content: bytes, media_type: str) -> dict[str, list[dict[str, object]]]:
	if media_type == "text/plain":
		return {"blocks": [block(1, decode_text(content))]}
	if media_type == "application/pdf":
		return extract_pdf_blocks(content)
	if media_type.endswith("wordprocessingml.document"):
		return {"blocks": [block(1, extract_docx_text(content))]}
	raise DocumentParseError("Unsupported resume document type")


def extract_pdf_blocks(content: bytes) -> dict[str, list[dict[str, object]]]:
	try:
		reader = PdfReader(BytesIO(content), strict=True)
	except Exception as error:
		raise DocumentParseError("Resume PDF could not be parsed") from error
	if reader.is_encrypted:
		raise DocumentParseError("Encrypted resume PDFs are not supported")
	if len(reader.pages) > MAX_PAGES:
		raise DocumentParseError("Resume PDF exceeds 100 pages")
	page_text = [page.extract_text() or "" for page in reader.pages]
	blocks = [block(index + 1, item) for index, item in enumerate(page_text)]
	if not any(item.strip() for item in page_text):
		raise DocumentParseError("Scanned or image-only resume PDFs are not supported")
	return {"blocks": blocks}


def extract_docx_text(content: bytes) -> str:
	try:
		with ZipFile(BytesIO(content)) as archive:
			document = archive.read("word/document.xml")
	except (BadZipFile, KeyError) as error:
		raise DocumentParseError("Resume DOCX could not be parsed") from error
	try:
		root = ElementTree.fromstring(document)
	except ElementTree.ParseError as error:
		raise DocumentParseError("Resume DOCX could not be parsed") from error
	paragraphs: list[str] = []
	for paragraph in root.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
		text = "".join(
			str(node.text or "")
			for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
		)
		if text.strip():
			paragraphs.append(text)
	if not paragraphs:
		raise DocumentParseError("Resume DOCX contains no extractable text")
	return "\n".join(paragraphs)


def decode_text(content: bytes) -> str:
	try:
		text = content.decode("utf-8-sig")
	except UnicodeDecodeError as error:
		raise DocumentParseError("Resume text is not UTF-8") from error
	if not text.strip():
		raise DocumentParseError("Resume text contains no extractable text")
	return text


def block(page: int, text: str) -> dict[str, object]:
	return {"id": f"p{page}-b1", "page": page, "text": text}
