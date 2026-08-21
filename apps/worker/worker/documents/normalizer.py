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
		"skills": [
			{"canonicalName": skill, "evidenceBlockIds": evidence}
			for skill, aliases in SKILL_ALIASES.items()
			if (evidence := matching_blocks(block_list, aliases))
		]
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
