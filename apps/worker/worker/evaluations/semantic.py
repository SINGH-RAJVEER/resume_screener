import hashlib
import math
from collections.abc import Mapping, Sequence


def text_hash(text: str) -> str:
	return hashlib.blake2b(text.encode(), digest_size=16).hexdigest()


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
	if len(a) != len(b):
		return 0.0
	dot = sum(x * y for x, y in zip(a, b))
	norm_a = math.sqrt(sum(x * x for x in a))
	norm_b = math.sqrt(sum(y * y for y in b))
	if norm_a == 0 or norm_b == 0:
		return 0.0
	return dot / (norm_a * norm_b)


def top_semantic_matches(
	requirement_vector: Sequence[float],
	block_vectors: Mapping[str, Sequence[float]],
	*,
	limit: int = 3,
	min_similarity: float = 0.3,
) -> list[dict[str, object]]:
	similarities = (
		(block_id, round(cosine_similarity(requirement_vector, vector), 4))
		for block_id, vector in block_vectors.items()
	)
	ranked = sorted(
		[
			(block_id, similarity)
			for block_id, similarity in similarities
			if similarity >= min_similarity
		],
		key=lambda item: item[1],
		reverse=True,
	)
	return [
		{"blockId": block_id, "similarity": similarity}
		for block_id, similarity in ranked[:limit]
	]
