"""Benchmark the resume parser against a repeatable synthetic corpus.

Real resume fixtures should be added under tests/fixtures/corpus and declared
in CORPUS_EXTENSIONS so the same benchmark measures them. The script prints
per-document outcomes and timings and exits nonzero when a document does not
match its expectation.
"""

import sys
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker.documents.parser import DocumentParseError, extract_blocks

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
CORPUS_EXTENSIONS = {".txt", ".pdf", ".docx"}


@dataclass(frozen=True)
class CorpusDocument:
	name: str
	content: bytes
	expect: str  # "parse" or "reject"


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
		page[NameObject("/Contents")] = stream
	output = BytesIO()
	writer.write(output)
	return output.getvalue()


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
				(72, 740, "ADA LOVELACE"),
				(72, 720, "Senior Platform Engineer at Example Corp."),
				(72, 700, "Built Python services and operated clusters."),
				(72, 680, "Led the platform team from 2020 to 2025."),
				(320, 740, "SKILLS"),
				(320, 720, "Python, Kubernetes, PostgreSQL."),
				(320, 700, "EDUCATION"),
				(320, 680, "BSc Computer Science."),
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
	documents = [
		CorpusDocument("synthetic-single-column.pdf", single_column, "parse"),
		CorpusDocument("synthetic-two-column.pdf", two_column, "parse"),
		CorpusDocument("synthetic-mixed-empty-page.pdf", mixed_pages, "parse"),
		CorpusDocument("synthetic-scanned.pdf", scanned, "reject"),
		CorpusDocument("synthetic-malformed.pdf", malformed, "reject"),
		CorpusDocument("synthetic-keyword-only.txt", keyword_txt, "parse"),
		CorpusDocument("synthetic-non-english.txt", non_english_txt, "reject"),
		CorpusDocument("synthetic-simple.docx", docx.getvalue(), "parse"),
	]
	for path in sorted(FIXTURE_DIR.iterdir()):
		if path.suffix in CORPUS_EXTENSIONS:
			documents.append(
				CorpusDocument(f"fixture-{path.name}", path.read_bytes(), "parse")
			)
	return documents


def run_benchmark() -> bool:
	documents = synthetic_corpus()
	print(f"{'document':44} {'result':7} {'state':16} blocks chars ms")
	all_matched = True
	for document in documents:
		started = time.perf_counter()
		try:
			parsed = extract_blocks(document.content, media_type_for(document.name))
		except DocumentParseError as error:
			elapsed = (time.perf_counter() - started) * 1000
			matched = document.expect == "reject"
			all_matched = all_matched and matched
			print(
				f"{document.name:44} {'reject' if matched else 'FAIL':7} "
				f"{'-':16} {'-':>6} {'-':>5} {elapsed:6.1f}  {error}"
			)
			continue
		elapsed = (time.perf_counter() - started) * 1000
		matched = document.expect == "parse"
		all_matched = all_matched and matched
		quality = parsed["quality"]
		print(
			f"{document.name:44} {'parse' if matched else 'FAIL':7} "
			f"{quality['state']:16} {parsed['metadata']['blockCount']:>6} "
			f"{parsed['metadata']['characterCount']:>5} {elapsed:6.1f}"
		)
	return all_matched


def media_type_for(name: str) -> str:
	if name.endswith(".pdf"):
		return "application/pdf"
	if name.endswith(".docx"):
		return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
	return "text/plain"


def main() -> None:
	if not run_benchmark():
		raise SystemExit(1)


if __name__ == "__main__":
	main()
