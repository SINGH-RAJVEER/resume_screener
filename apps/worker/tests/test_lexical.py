from worker.evaluations.lexical import lexical_tokens, top_lexical_matches

BLOCKS = {
	"b1": "Built Python services with PostgreSQL and Docker in production.",
	"b2": "Led a team of four engineers across two product squads.",
	"b3": "Wrote Kubernetes operators in Go and deployed them with Helm.",
}


def test_ranks_exact_terminology_first() -> None:
	matches = top_lexical_matches("Experience operating PostgreSQL databases", BLOCKS)
	assert matches[0]["blockId"] == "b1"
	assert matches[0]["score"] > 0


def test_filters_blocks_without_shared_terms() -> None:
	matches = top_lexical_matches("Kubernetes and Helm experience", {"b2": BLOCKS["b2"]})
	assert matches == []


def test_limits_results() -> None:
	blocks = {
		**BLOCKS,
		"b4": "PostgreSQL performance tuning and backup automation.",
		"b5": "PostgreSQL replication setup.",
	}
	matches = top_lexical_matches("PostgreSQL administration", blocks)
	assert len(matches) <= 3
	# Shorter blocks with denser terminology outrank the longer mixed block.
	assert [match["blockId"] for match in matches] == ["b5", "b4", "b1"]
	scores = [float(match["score"]) for match in matches]
	assert scores == sorted(scores, reverse=True)


def test_stopwords_do_not_create_matches() -> None:
	assert lexical_tokens("The will of our teams") == ["teams"]


def test_empty_requirement_returns_no_matches() -> None:
	assert top_lexical_matches("with the and", BLOCKS) == []
