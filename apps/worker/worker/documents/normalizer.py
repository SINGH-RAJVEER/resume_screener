from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

SKILL_ALIASES: dict[str, tuple[str, ...]] = {
	"AWS": ("aws", "amazon web services"),
	"Docker": ("docker",),
	"JavaScript": ("javascript", "js"),
	"Kubernetes": ("kubernetes", "k8s"),
	"PostgreSQL": ("postgresql", "postgres"),
	"Python": ("python",),
	"React": ("react", "reactjs", "react.js"),
	"SQL": ("sql",),
	"TypeScript": ("typescript", "ts"),
}


def normalize_resume(blocks: Iterable[Mapping[str, object]]) -> dict[str, object]:
	block_list = list(blocks)
	return {
		"contact": contact_facts(block_list),
		"skills": [
			{"canonicalName": skill, "evidenceBlockIds": evidence}
			for skill, aliases in SKILL_ALIASES.items()
			if (evidence := matching_blocks(block_list, aliases))
		]
	}


def contact_facts(blocks: Iterable[Mapping[str, object]]) -> dict[str, str | None]:
	lines = [str(block["text"]).strip() for block in blocks if str(block["text"]).strip()]
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


def matching_blocks(blocks: Iterable[Mapping[str, object]], aliases: Iterable[str]) -> list[str]:
	pattern = re.compile(
		"|".join(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])" for alias in aliases),
		re.IGNORECASE,
	)
	return [
		str(block["id"])
		for block in blocks
		if pattern.search(str(block["text"]))
	]
