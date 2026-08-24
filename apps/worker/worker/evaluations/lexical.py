"""Per-requirement lexical evidence retrieval over resume blocks.

Pure-Python TF-IDF cosine ranking. The product does not use PostgreSQL
full-text search, so this runs in application code and needs no provider
or extension; it complements semantic retrieval when embeddings are
unavailable or weak on exact terminology.
"""

import math
from collections import Counter
from collections.abc import Mapping

from ..documents.vocabulary import TOKEN_PATTERN

# Function words that carry no screening signal.
STOP_TOKENS = frozenset(
	"a an and are as at be by for from in is of on or our that the to we will with you your"
	.split()
)


def lexical_tokens(text: str) -> list[str]:
	return [
		token
		for token in TOKEN_PATTERN.findall(text.casefold())
		if len(token) > 1 and token not in STOP_TOKENS
	]


def top_lexical_matches(
	requirement_text: str,
	block_texts: Mapping[str, str],
	*,
	limit: int = 3,
	min_score: float = 0.08,
) -> list[dict[str, object]]:
	block_tokens = {
		block_id: Counter(lexical_tokens(text))
		for block_id, text in block_texts.items()
		if lexical_tokens(text)
	}
	if not block_tokens:
		return []
	document_frequency = Counter(
		token for counts in block_tokens.values() for token in counts
	)
	total_blocks = len(block_tokens)

	def idf(token: str) -> float:
		return math.log((total_blocks + 1) / (document_frequency[token] + 1)) + 1

	def tfidf_vector(counts: Counter[str]) -> dict[str, float]:
		return {token: count * idf(token) for token, count in counts.items()}

	def cosine(left: Mapping[str, float], right: Mapping[str, float]) -> float:
		dot = sum(weight * right.get(token, 0) for token, weight in left.items())
		norm_left = math.sqrt(sum(weight * weight for weight in left.values()))
		norm_right = math.sqrt(sum(weight * weight for weight in right.values()))
		if norm_left == 0 or norm_right == 0:
			return 0.0
		return dot / (norm_left * norm_right)

	requirement_vector = tfidf_vector(Counter(lexical_tokens(requirement_text)))
	scored = [
		(block_id, round(cosine(requirement_vector, tfidf_vector(counts)), 4))
		for block_id, counts in block_tokens.items()
	]
	ranked = sorted(
		[item for item in scored if item[1] >= min_score],
		key=lambda item: item[1],
		reverse=True,
	)
	return [{"blockId": block_id, "score": score} for block_id, score in ranked[:limit]]
