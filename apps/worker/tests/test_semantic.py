from typing import SupportsFloat, cast

from worker.evaluations.semantic import (
	cosine_similarity,
	text_hash,
	top_semantic_matches,
)


def test_text_hash_is_stable_and_hex() -> None:
	assert text_hash("hello") == text_hash("hello")
	assert text_hash("hello") != text_hash("world")
	assert len(text_hash("hello")) == 32


def test_cosine_similarity_basics() -> None:
	assert cosine_similarity([1, 0], [1, 0]) == 1.0
	assert cosine_similarity([1, 0], [0, 1]) == 0.0
	assert abs(cosine_similarity([1, 2], [1, 2]) - 1.0) < 1e-9
	# Dimension mismatch means no comparison is possible.
	assert cosine_similarity([1], [1, 0]) == 0.0
	assert cosine_similarity([0, 0], [0, 0]) == 0.0


def test_top_semantic_matches_filters_and_ranks() -> None:
	requirement = [1.0, 0.0]
	blocks = {
		"strong": [0.9, 0.1],
		"weak": [0.0, 1.0],
		"moderate": [0.5, 0.5],
	}
	matches = top_semantic_matches(requirement, blocks, min_similarity=0.3)
	assert [item["blockId"] for item in matches] == ["strong", "moderate"]
	similarities = [float(cast("SupportsFloat", item["similarity"])) for item in matches]
	assert similarities[0] > similarities[1]


def test_top_semantic_matches_limits_results() -> None:
	requirement = [1.0, 0.0]
	blocks = {f"b{i}": [0.5 + i * 0.01, 0.5] for i in range(6)}
	matches = top_semantic_matches(requirement, blocks, limit=2)
	assert len(matches) == 2
