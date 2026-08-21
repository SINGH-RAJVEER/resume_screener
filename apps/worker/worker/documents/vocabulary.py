"""Corpus-backed skill vocabulary with deterministic phrase matching."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import cast

CORPUS_PATH = Path(__file__).with_name("skills_corpus.json")

# Tokens keep internal punctuation used by skill names: c++, c#, node.js,
# ci/cd, t-sql. Dot/slash/hyphen runs must continue into alphanumerics so
# sentence punctuation stays outside; plus/hash runs may end a token.
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[.#/-]+[a-z0-9]+|[+#]+)*")
MAX_PHRASE_TOKENS = 6


class SkillVocabulary:
	def __init__(self, phrases: dict[str, str], categories: dict[str, str | None]) -> None:
		self.phrase_to_canonical = phrases
		self.categories = categories
		self.max_tokens = min(
			max(len(phrase.split()) for phrase in phrases),
			MAX_PHRASE_TOKENS,
		)

	def mention(self, text: str) -> dict[str, list[str]]:
		"""Match skill phrases longest-first. Returns canonical name -> matched phrases."""
		tokens = TOKEN_PATTERN.findall(text.casefold())
		found: dict[str, list[str]] = {}
		index = 0
		while index < len(tokens):
			match_count = 0
			for count in range(min(self.max_tokens, len(tokens) - index), 0, -1):
				phrase = " ".join(tokens[index : index + count])
				canonical = self.phrase_to_canonical.get(phrase)
				if canonical is not None:
					spans = found.setdefault(canonical, [])
					if phrase not in spans:
						spans.append(phrase)
					match_count = count
					break
			index += match_count or 1
		return found

	def category_for(self, canonical_name: str) -> str | None:
		return self.categories.get(canonical_name.casefold())


@lru_cache(maxsize=1)
def load_vocabulary() -> SkillVocabulary:
	corpus = cast(dict[str, object], json.loads(CORPUS_PATH.read_text()))
	raw_skills = cast(list[dict[str, object]], corpus["skills"])
	raw_aliases = cast(dict[str, str], corpus["aliases"])
	categories: dict[str, str | None] = {}
	phrases: dict[str, str] = {}
	for skill in raw_skills:
		name = str(skill["name"])
		category = skill.get("category")
		key = name.casefold()
		categories[key] = str(category) if category is not None else None
		phrases[key] = name
	for alias, canonical in raw_aliases.items():
		if canonical.casefold() not in categories:
			raise ValueError(f"Alias {alias!r} targets unknown skill {canonical!r}")
		phrases[alias.casefold()] = canonical
	return SkillVocabulary(phrases, categories)


def mentioned_skills(text: str) -> set[str]:
	"""Canonical skill names mentioned in free text such as job requirements."""
	return set(load_vocabulary().mention(text))
