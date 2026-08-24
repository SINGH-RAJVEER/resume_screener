"""Unsupported-claim measurement for resume-extraction artifacts.

Schema-valid model output can still contain invented values. This module
quantifies that risk: every extracted assessment-fact value must occur
inside its own cited evidence quotes, and those quotes must exist in the
source blocks they cite. The resulting rates feed release comparisons when
prompts, schemas, or models change.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

CLAIM_TEXT_FIELDS: dict[str, tuple[str, ...]] = {
	"contact": ("name", "email", "phone", "location"),
	"skills": ("canonicalName", "sourceText"),
	"employment": ("employer", "title"),
	"education": ("institution", "degree", "fieldOfStudy"),
	"certifications": ("name",),
}


@dataclass(frozen=True)
class CollectionClaims:
	total: int
	invalid_citations: int
	ungrounded_values: int


@dataclass(frozen=True)
class ClaimReport:
	collections: Mapping[str, CollectionClaims]
	examples: tuple[str, ...]

	@property
	def total_claims(self) -> int:
		return sum(item.total for item in self.collections.values())

	@property
	def unsupported_claims(self) -> int:
		return sum(
			item.invalid_citations + item.ungrounded_values
			for item in self.collections.values()
		)

	@property
	def rate(self) -> float | None:
		if not self.total_claims:
			return None
		return self.unsupported_claims / self.total_claims


def measure_unsupported_claims(
	facts: Mapping[str, object], block_texts: Mapping[str, str]
) -> ClaimReport:
	reports: dict[str, CollectionClaims] = {}
	examples: list[str] = []
	for collection, text_fields in CLAIM_TEXT_FIELDS.items():
		total = 0
		invalid_citations = 0
		ungrounded_values = 0
		for entry in _entries(facts.get(collection)):
			valid_quotes = _valid_quotes(entry, block_texts)
			for field in text_fields:
				value = entry.get(field)
				if not isinstance(value, str) or not value.strip():
					continue
				total += 1
				if not valid_quotes:
					invalid_citations += 1
					examples.append(f"{collection}.{field}: {value}")
				elif value.casefold() not in "\n".join(valid_quotes).casefold():
					ungrounded_values += 1
					examples.append(f"{collection}.{field}: {value}")
		if total:
			reports[collection] = CollectionClaims(total, invalid_citations, ungrounded_values)
	return ClaimReport(reports, tuple(examples[:20]))


def _valid_quotes(entry: Mapping[str, Any], block_texts: Mapping[str, str]) -> list[str]:
	evidence = entry.get("evidence")
	if not isinstance(evidence, list):
		return []
	quotes: list[str] = []
	for item in cast(list[object], evidence):
		if not isinstance(item, Mapping):
			continue
		citation = cast(Mapping[str, Any], item)
		quote = str(citation.get("quote") or "")
		block_text = block_texts.get(str(citation.get("blockId") or ""))
		if not quote or block_text is None or quote not in block_text:
			continue
		quotes.append(quote)
	return quotes


def _entries(value: object) -> list[Mapping[str, Any]]:
	if isinstance(value, Mapping):
		return [cast(Mapping[str, Any], value)]
	if not isinstance(value, list):
		return []
	return [
		cast(Mapping[str, Any], item) for item in cast(list[object], value)
		if isinstance(item, Mapping)
	]
