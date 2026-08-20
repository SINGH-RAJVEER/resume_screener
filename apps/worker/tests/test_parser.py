from io import BytesIO
from zipfile import ZipFile

import pytest

from worker.parser import DocumentParseError, extract_blocks


def test_extracts_utf8_text_into_an_evidence_block() -> None:
	blocks = extract_blocks(b"Ada Lovelace\nPython engineer", "text/plain")

	assert blocks == {
		"blocks": [{"id": "p1-b1", "page": 1, "text": "Ada Lovelace\nPython engineer"}]
	}


def test_extracts_docx_paragraphs() -> None:
	content = BytesIO()
	with ZipFile(content, "w") as archive:
		archive.writestr(
			"word/document.xml",
			"""<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
			<w:body><w:p><w:r><w:t>Python engineer</w:t></w:r></w:p></w:body></w:document>""",
		)

	blocks = extract_blocks(
		content.getvalue(),
		"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	)

	assert blocks["blocks"][0]["text"] == "Python engineer"


def test_rejects_empty_text_documents() -> None:
	with pytest.raises(DocumentParseError, match="no extractable text"):
		extract_blocks(b" \n", "text/plain")
