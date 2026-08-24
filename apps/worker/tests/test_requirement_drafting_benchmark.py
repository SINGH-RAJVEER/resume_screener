import json

from scripts.benchmark_requirement_drafting import (
	DATASET_PATH,
	greedy_match,
	main,
	similarity,
)

DATASET_SIZE = 6


def load_cases() -> list[dict[str, object]]:
	return [
		json.loads(line)
		for line in DATASET_PATH.read_text().splitlines()
		if line.strip()
	]


def test_every_case_is_double_annotated_with_text_and_kind() -> None:
	cases = load_cases()
	assert len(cases) == DATASET_SIZE
	for case in cases:
		assert case["sourceText"] and case["id"]
		annotations = case["annotations"]
		assert isinstance(annotations, dict)
		assert set(annotations) == {"annotatorA", "annotatorB"}
		for labels in annotations.values():
			assert isinstance(labels, list)
			assert labels
			assert all(
				isinstance(label, dict) and label.get("text") and label.get("kind")
				for label in labels
			)


def test_paraphrases_match_and_unrelated_labels_do_not() -> None:
	assert (
		similarity("3 years React experience", "3 years building interfaces with React")
		>= 0.5
	)
	assert similarity("SQL fluency required", "Kubernetes cluster upgrades") < 0.2


def test_greedy_matching_never_reuses_a_label_or_draft() -> None:
	drafts = ["Python experience", "Python experience"]
	labels = ["Python skills", "Other skills"]
	matched = greedy_match(drafts, labels)
	# Only one label clears the similarity bar; the duplicate draft stays
	# unmatched instead of pairing twice with the same label.
	assert len(matched) == 1


def test_dataset_meets_release_thresholds(capsys: object) -> None:
	# The release gate runs against the checked-in dataset exactly as the
	# script does, so compiler regressions fail tests before release.
	exit_code = main()
	assert exit_code == 0
	assert capsys is not None  # output asserted indirectly through exit code
