from worker.documents.vocabulary import load_vocabulary, mentioned_skills


def test_matches_multi_word_phrases_and_abbreviations() -> None:
	found = mentioned_skills("Experience with Amazon Web Services, k8s and Node.js required.")

	assert found == {"AWS", "Kubernetes", "Node.js"}


def test_prefers_longest_phrase_at_each_position() -> None:
	vocabulary = load_vocabulary()
	found = vocabulary.mention("microsoft azure")

	# "azure" is also a skill; the longer phrase must win the span.
	assert list(found) == ["Azure"]


def test_keeps_punctuation_inside_skill_tokens() -> None:
	found = mentioned_skills("Built c++ services and wrote Microsoft ASP.NET apps.")

	assert found == {"C++", "Microsoft ASP.NET"}


def test_does_not_match_partial_words() -> None:
	found = mentioned_skills("The pythonic approach to management of staging.")

	# No standalone skill tokens appear; substrings inside words never match.
	assert "Python" not in found


def test_absorbed_phrases_do_not_become_skills() -> None:
	found = mentioned_skills("B.Tech Computer Science, VJTI Mumbai, 2018.")

	# "Science" is a cross-domain element but education mentions are absorbed.
	assert found == set()


def test_corpus_aliases_target_known_skills() -> None:
	vocabulary = load_vocabulary()
	known = {name.casefold() for name in vocabulary.categories}

	for alias, canonical in vocabulary.phrase_to_canonical.items():
		assert alias == canonical.casefold() or canonical.casefold() in known, (
			f"alias {alias!r} targets unknown skill {canonical!r}"
		)
