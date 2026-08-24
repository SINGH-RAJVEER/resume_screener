from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from .normalizer import normalize_resume
from .parser import EvidenceBlock, ParsedDocument, extract_blocks


@dataclass(frozen=True)
class PreparedDocument:
	artifact: ParsedDocument
	normalized_facts: dict[str, object]

	@property
	def blocks(self) -> list[EvidenceBlock]:
		return self.artifact["blocks"]

	@property
	def quality_state(self) -> Literal["ready", "review_required"]:
		return self.artifact["quality"]["state"]

	@property
	def warnings(self) -> list[str]:
		return list(self.artifact["quality"]["warnings"])


def prepare_document(content: bytes, media_type: str) -> PreparedDocument:
	artifact = extract_blocks(content, media_type)
	facts = normalize_resume(artifact["blocks"])
	facts["warnings"] = list(artifact["quality"]["warnings"])
	return PreparedDocument(artifact=artifact, normalized_facts=facts)


def add_document_warnings(
	facts: Mapping[str, object], warnings: Sequence[str]
) -> dict[str, object]:
	existing = facts.get("warnings")
	merged: list[str] = []
	for warning in [
		*warnings,
		*(cast(list[object], existing) if isinstance(existing, list) else []),
	]:
		if isinstance(warning, str) and warning not in merged:
			merged.append(warning)
	return {**facts, "warnings": merged}
