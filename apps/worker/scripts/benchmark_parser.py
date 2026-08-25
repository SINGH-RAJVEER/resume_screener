"""Benchmark candidate PDF parsers against a repeatable corpus.

The corpus combines synthetic documents built at run time with checked-in
fixtures under tests/fixtures/corpus declared in expectations.json. Real
resume fixtures belong there too so every candidate parser measures them.

TXT and DOCX share one code path across options; the comparison targets PDF
extraction. The layout option is the production extractor. The remaining
options wrap alternative libraries behind the same block interface and are
only installed with the `benchmark` dependency group.

Usage: uv run python scripts/benchmark_parser.py [--parser layout|pypdf|pdfminer|pymupdf]
"""

import json
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker.documents.parser import (
	DocumentParseError,
	evidence_block,
	extract_blocks,
	normalize_text,
	parsed_document,
)

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
CORPUS_DIR = FIXTURE_DIR / "corpus"
CORPUS_EXTENSIONS = {".txt", ".pdf", ".docx"}
PDF_MEDIA_TYPE = "application/pdf"

# Malformed corpus documents make pypdf log recovery warnings that are
# expected benchmark output, not failures.
logging.getLogger("pypdf").setLevel(logging.CRITICAL)


@dataclass(frozen=True)
class CorpusDocument:
	name: str
	content: bytes
	expect: str  # "parse" or "reject"
	order_check: Callable[[str], bool] | None = None


def placed_pdf(pages: list[list[tuple[float, float, str]] | None]) -> bytes:
	writer = PdfWriter()
	for placements in pages:
		page = writer.add_blank_page(width=612, height=792)
		if not placements:
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
		commands = "\n".join(
			f"BT /F1 12 Tf {x} {y} Td ({text}) Tj ET" for x, y, text in placements
		)
		stream = DecodedStreamObject()
		stream.set_data(commands.encode())
		# Stream objects must be indirect references; direct streams are
		# ignored by stricter readers such as pdfminer.
		page[NameObject("/Contents")] = writer._add_object(stream)
	output = BytesIO()
	writer.write(output)
	return output.getvalue()


def two_column_reading_order(text: str) -> bool:
	# Column-major extraction keeps sidebar skills after the experience
	# narrative; row-major interleaving places them between title lines.
	return (
		"Built Python services" in text
		and "Python, Kubernetes" in text
		and text.index("Python, Kubernetes") > text.index("Built Python services")
	)


def synthetic_corpus() -> list[CorpusDocument]:
	resume_lines = [
		"Ada Lovelace",
		"ada@example.com",
		"Location: London, United Kingdom",
		"Experience",
		"Senior Platform Engineer, Example Corp",
		"Built Python services and operated Kubernetes clusters from 2020 to 2025.",
		"Education",
		"BSc Computer Science, Example University",
	]
	single_column = placed_pdf(
		[[(72, 740 - index * 18, line) for index, line in enumerate(resume_lines)]]
	)
	two_column = placed_pdf(
		[
			[
				# The sidebar is drawn first so raw content-stream order
				# contradicts visual reading order, as real exports do.
				(320, 740, "SKILLS"),
				(320, 720, "Python, Kubernetes, PostgreSQL."),
				(320, 700, "EDUCATION"),
				(320, 680, "BSc Computer Science."),
				(72, 740, "ADA LOVELACE"),
				(72, 720, "Senior Platform Engineer at Example Corp."),
				(72, 700, "Built Python services and operated clusters."),
				(72, 680, "Led the platform team from 2020 to 2025."),
			]
		]
	)
	mixed_pages = placed_pdf(
		[
			[(72, 740, "Ada Lovelace, senior platform engineer with ten years of experience.")],
			None,
		]
	)
	scanned = placed_pdf([None])
	malformed = b"%PDF-1.7\nnot a complete PDF"
	keyword_txt = b"KUBERNETES DOCKER REDIS KAFKA TERRAFORM POSTGRESQL GRPC GRAPHQL"
	non_english_txt = (
		"Softwareentwickler mit zehn Jahren Erfahrung im Entwurf verteilter "
		"Systeme und der Leitung von Plattformteams für ein reguliertes Umfeld "
		"mit Fokus auf Zuverlässigkeit".encode()
	)
	docx = BytesIO()
	with ZipFile(docx, "w") as archive:
		archive.writestr(
			"[Content_Types].xml",
			"<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>",
		)
		archive.writestr(
			"word/document.xml",
			"""<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
			<w:body>
				<w:p><w:r><w:t>Ada Lovelace</w:t></w:r></w:p>
				<w:p><w:r><w:t>Senior platform engineer who built services.</w:t></w:r></w:p>
			</w:body></w:document>""",
		)
	return [
		CorpusDocument("synthetic-single-column.pdf", single_column, "parse"),
		CorpusDocument("synthetic-two-column.pdf", two_column, "parse", two_column_reading_order),
		CorpusDocument("synthetic-mixed-empty-page.pdf", mixed_pages, "parse"),
		CorpusDocument("synthetic-scanned.pdf", scanned, "reject"),
		CorpusDocument("synthetic-malformed.pdf", malformed, "reject"),
		CorpusDocument("synthetic-keyword-only.txt", keyword_txt, "parse"),
		CorpusDocument("synthetic-non-english.txt", non_english_txt, "reject"),
		CorpusDocument("synthetic-simple.docx", docx.getvalue(), "parse"),
	]


def fixture_corpus() -> list[CorpusDocument]:
	documents: list[CorpusDocument] = []
	for path in sorted(CORPUS_DIR.iterdir()):
		if path.suffix not in CORPUS_EXTENSIONS:
			continue
		expectation = declared_expectations().get(path.name)
		if expectation is None:
			raise SystemExit(f"No expectation declared for corpus fixture {path.name}")
		documents.append(
			CorpusDocument(
				f"fixture-{path.name}",
				path.read_bytes(),
				expectation,
				two_column_reading_order if path.stem.endswith("two-column") else None,
			)
		)
	for path in sorted(FIXTURE_DIR.iterdir()):
		if path.suffix in CORPUS_EXTENSIONS:
			documents.append(
				CorpusDocument(f"fixture-{path.name}", path.read_bytes(), "parse")
			)
	return documents


_EXPECTATIONS: dict[str, str] | None = None


def declared_expectations() -> dict[str, str]:
	global _EXPECTATIONS
	if _EXPECTATIONS is None:
		manifest = CORPUS_DIR / "expectations.json"
		_EXPECTATIONS = json.loads(manifest.read_text())
	return _EXPECTATIONS


# PDF extraction backends. Each returns evidence blocks plus the page count
# and raises DocumentParseError for rejected documents. Shared checks such as
# language detection and duplicate warnings run in parsed_document.


def pdf_layout(content: bytes) -> tuple[list, int]:
	parsed = extract_blocks(content, PDF_MEDIA_TYPE)
	return parsed["blocks"], parsed["metadata"]["pageCount"]


def pdf_pypdf_text(content: bytes) -> tuple[list, int]:
	try:
		reader = PdfReader(BytesIO(content), strict=True)
		if reader.is_encrypted:
			raise DocumentParseError("Encrypted resume PDFs are not supported")
		blocks = []
		for page_number, page in enumerate(reader.pages, start=1):
			text = normalize_text(str(page.extract_text() or ""), allow_empty=True).strip()
			if text:
				blocks.append(evidence_block(page_number, len(blocks) + 1, text, "pdf_text", None))
	except DocumentParseError:
		raise
	except Exception as error:
		raise DocumentParseError("Resume PDF could not be parsed") from error
	if not blocks:
		raise DocumentParseError("Scanned or image-only resume PDFs are not supported")
	return blocks, len(reader.pages)


def pdf_pdfminer(content: bytes) -> tuple[list, int]:
	try:
		from pdfminer.high_level import extract_text

		reader = PdfReader(BytesIO(content), strict=False)
		blocks = []
		for page_number in range(len(reader.pages)):
			text = normalize_text(
				# pdfminer separates pages with form feeds; treat them as
				# paragraph breaks like every other whitespace signal.
				(extract_text(BytesIO(content), page_numbers=[page_number]) or "").replace(
					"\x0c", "\n"
				),
				allow_empty=True,
			).strip()
			if text:
				blocks.append(
					evidence_block(page_number + 1, len(blocks) + 1, text, "pdf_text", None)
				)
	except DocumentParseError:
		raise
	except Exception as error:
		raise DocumentParseError("Resume PDF could not be parsed") from error
	if not blocks:
		raise DocumentParseError("Scanned or image-only resume PDFs are not supported")
	return blocks, len(reader.pages)


def pdf_pymupdf(content: bytes) -> tuple[list, int]:
	try:
		import pymupdf

		document = pymupdf.open(stream=content, filetype="pdf")
		if document.needs_pass:
			raise DocumentParseError("Encrypted resume PDFs are not supported")
		blocks = []
		for page_number, page in enumerate(document, start=1):
			raw = sorted(page.get_text("blocks"), key=lambda block: (block[1], block[0]))
			for x0, y0, x1, y1, text, *_ in raw:
				clean = normalize_text(text, allow_empty=True).strip()
				if clean:
					blocks.append(
						evidence_block(
							page_number, len(blocks) + 1, clean, "pdf_text", [x0, y0, x1, y1]
						)
					)
	except DocumentParseError:
		raise
	except Exception as error:
		raise DocumentParseError("Resume PDF could not be parsed") from error
	if not blocks:
		raise DocumentParseError("Scanned or image-only resume PDFs are not supported")
	return blocks, document.page_count


PARSERS: dict[str, Callable[[bytes], tuple[list, int]]] = {
	"layout": pdf_layout,
	"pypdf": pdf_pypdf_text,
	"pdfminer": pdf_pdfminer,
	"pymupdf": pdf_pymupdf,
}


def parse_with(parser: str, document: CorpusDocument) -> dict:
	content = document.content
	media_type = media_type_for(document.name)
	if media_type != PDF_MEDIA_TYPE:
		return extract_blocks(content, media_type)
	blocks, page_count = PARSERS[parser](content)
	return parsed_document(blocks, media_type=media_type, page_count=page_count)


def run_benchmark(parser_names: list[str]) -> bool:
	documents = synthetic_corpus() + fixture_corpus()
	all_matched = True
	summaries: list[tuple[str, int, int, float]] = []
	for parser in parser_names:
		print(f"\n== parser: {parser} ==")
		print(f"{'document':44} {'result':7} {'state':16} blocks chars ms")
		passed = 0
		pdf_millis = 0.0
		pdf_runs = 0
		for document in documents:
			started = time.perf_counter()
			try:
				parsed = parse_with(parser, document)
			except DocumentParseError as error:
				elapsed = (time.perf_counter() - started) * 1000
				matched = document.expect == "reject"
				all_matched = all_matched and matched
				passed += matched
				print(
					f"{document.name:44} {'reject' if matched else 'FAIL':7} "
					f"{'-':16} {'-':>6} {'-':>5} {elapsed:6.1f}  {error}"
				)
				continue
			elapsed = (time.perf_counter() - started) * 1000
			text = "\n".join(block["text"] for block in parsed["blocks"])
			matched = (
				document.expect == "parse"
				and (document.order_check is None or document.order_check(text))
			)
			all_matched = all_matched and matched
			passed += matched
			if document.name.endswith(".pdf"):
				pdf_millis += elapsed
				pdf_runs += 1
			print(
				f"{document.name:44} {'parse' if matched else 'FAIL':7} "
				f"{parsed['quality']['state']:16} {parsed['metadata']['blockCount']:>6} "
				f"{parsed['metadata']['characterCount']:>5} {elapsed:6.1f}"
			)
		summaries.append((parser, passed, len(documents), pdf_millis / max(pdf_runs, 1)))
	print("\n== summary ==")
	print(f"{'parser':12} {'passed':>7} {'total':>6} {'avg pdf ms':>11}")
	for parser, passed, total, average in summaries:
		print(f"{parser:12} {passed:>7} {total:>6} {average:>11.1f}")
	return all_matched


def media_type_for(name: str) -> str:
	if name.endswith(".pdf"):
		return PDF_MEDIA_TYPE
	if name.endswith(".docx"):
		return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
	return "text/plain"


def main() -> None:
	parser_names = list(PARSERS)
	if "--parser" in sys.argv:
		option = sys.argv[sys.argv.index("--parser") + 1]
		parser_names = [option]
	if unknown := [name for name in parser_names if name not in PARSERS]:
		raise SystemExit(f"Unknown parser option: {', '.join(unknown)}")
	if not run_benchmark(parser_names):
		raise SystemExit(1)


if __name__ == "__main__":
	main()
