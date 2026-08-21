
import re
from collections.abc import Iterable, Mapping

from .vocabulary import load_vocabulary


def normalize_resume(blocks: Iterable[Mapping[str, object]]) -> dict[str, object]:
	block_list = list(blocks)
	vocabulary = load_vocabulary()
	skill_hits: dict[str, list[str]] = {}
	for block in block_list:
		block_id = str(block["id"])
		for canonical_name in vocabulary.mention(str(block["text"])):
			ids = skill_hits.setdefault(canonical_name, [])
			if block_id not in ids:
				ids.append(block_id)
	return {
		"contact": contact_facts(block_list),
		"skills": [
			{
				"canonicalName": canonical_name,
				"category": vocabulary.category_for(canonical_name),
				"evidenceBlockIds": sorted(
					skill_hits[canonical_name], key=block_order(block_list)
				),
			}
			for canonical_name in sorted(skill_hits, key=str.casefold)
		],
	}


def block_order(blocks: list[Mapping[str, object]]):
	order = {str(block["id"]): index for index, block in enumerate(blocks)}

	def key(block_id: str) -> int:
		return order.get(block_id, len(order))

	return key


def contact_facts(blocks: Iterable[Mapping[str, object]]) -> dict[str, str | None]:
	# Blocks are page- or document-granular; contact heuristics work on lines.
	lines = [
		line.strip()
		for block in blocks
		for line in str(block["text"]).splitlines()
		if line.strip()
	]
	combined = "\n".join(lines)
	email_match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", combined, re.IGNORECASE)
	first_line = lines[0] if lines else ""
	name_words = first_line.split()
	name = (
		first_line
		if 2 <= len(name_words) <= 5
		and re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,80}", first_line)
		and all(word[0].isupper() for word in name_words)
		else None
	)
	location = next(
		(
			line.removeprefix("Location:").strip()
			for line in lines[:12]
			if line.casefold().startswith("location:")
		),
		None,
	)
	return {
		"name": name,
		"email": email_match.group(0) if email_match else None,
		"location": location,
	}
