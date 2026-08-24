"""Benchmark requirement drafting against a double-annotated dataset.

Each dataset case carries two independent annotator label sets. The script
compiles deterministic drafts for every description, matches drafts to each
annotator's labels with greedy Dice-similarity pairing, and reports
precision, recall, F1, kind-classification accuracy over matched pairs, and
the inter-annotator agreement ceiling. It exits nonzero when aggregate F1 or
kind accuracy falls below the release thresholds in THRESHOLDS.

Add cases to scripts/data/requirement_drafting_dataset.jsonl; every new case
must carry two annotation sets so agreement stays measurable.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker.evaluations.lexical import lexical_tokens
from worker.job_descriptions.compiler import compile_job_description

DATASET_PATH = Path(__file__).resolve().parent / "data" / "requirement_drafting_dataset.jsonl"

# Release gates. Drafting quality must stay within reach of human agreement:
# F1 against either annotator cannot fall far below what the two annotators
# achieve with each other.
THRESHOLDS = {
	"min_f1_vs_annotator": 0.60,
	"min_kind_accuracy": 0.70,
	"min_inter_annotator_f1": 0.60,
}
MATCH_THRESHOLD = 0.5


@dataclass(frozen=True)
class CaseMetrics:
	case_id: str
	precision_a: float
	recall_a: float
	f1_a: float
	precision_b: float
	recall_b: float
	f1_b: float
	kind_accuracy: float


def similarity(left: str, right: str) -> float:
	left_tokens = set(lexical_tokens(left))
	right_tokens = set(lexical_tokens(right))
	if not left_tokens or not right_tokens:
		return 0.0
	return 2 * len(left_tokens & right_tokens) / (len(left_tokens) + len(right_tokens))


def greedy_match(
	drafts: list[str], labels: list[str]
) -> list[tuple[int, int]]:
	pairs = sorted(
		(
			(similarity(drafts[draft_index], labels[label_index]), draft_index, label_index)
			for draft_index in range(len(drafts))
			for label_index in range(len(labels))
		),
		reverse=True,
	)
	matched: list[tuple[int, int]] = []
	used_drafts: set[int] = set()
	used_labels: set[int] = set()
	for score, draft_index, label_index in pairs:
		if score < MATCH_THRESHOLD:
			break
		if draft_index in used_drafts or label_index in used_labels:
			continue
		matched.append((draft_index, label_index))
		used_drafts.add(draft_index)
		used_labels.add(label_index)
	return matched


def prf(matches: int, predictions: int, references: int) -> tuple[float, float, float]:
	precision = matches / predictions if predictions else 0.0
	recall = matches / references if references else 0.0
	f1 = (
		2 * precision * recall / (precision + recall)
		if precision + recall
		else 0.0
	)
	return precision, recall, f1


def evaluate_case(case: dict[str, object]) -> CaseMetrics:
	source = str(case["sourceText"])
	artifact = compile_job_description(source, degraded=True)
	drafts = [
		str(requirement.get("normalizedText", ""))
		for requirement in artifact["requirements"]
	]
	kinds = {
		index: str(requirement.get("suggestedKind", ""))
		for index, requirement in enumerate(artifact["requirements"])
	}
	annotations = cast(dict[str, object], case["annotations"])
	labels_a = cast(list[dict[str, object]], annotations["annotatorA"])
	labels_b = cast(list[dict[str, object]], annotations["annotatorB"])

	def metrics_for(
		labels: list[dict[str, object]]
	) -> tuple[float, float, float, float]:
		label_texts = [str(label["text"]) for label in labels]
		matched = greedy_match(drafts, label_texts)
		precision, recall, f1 = prf(len(matched), len(drafts), len(labels))
		correct_kinds = sum(
			kinds[draft_index] == str(labels[label_index].get("kind", ""))
			for draft_index, label_index in matched
		)
		kind_accuracy = correct_kinds / len(matched) if matched else 0.0
		return precision, recall, f1, kind_accuracy

	precision_a, recall_a, f1_a, kind_a = metrics_for(labels_a)
	precision_b, recall_b, f1_b, kind_b = metrics_for(labels_b)
	agreement_pairs = greedy_match(
		[str(label["text"]) for label in labels_a],
		[str(label["text"]) for label in labels_b],
	)
	_, _, agreement = prf(len(agreement_pairs), len(labels_a), len(labels_b))
	print(
		f"{case['id']}: A p={precision_a:.2f} r={recall_a:.2f} f1={f1_a:.2f} | "
		f"B p={precision_b:.2f} r={recall_b:.2f} f1={f1_b:.2f} | "
		f"kind={max(kind_a, kind_b):.2f} | agreement={agreement:.2f}"
	)
	return CaseMetrics(
		str(case["id"]),
		precision_a,
		recall_a,
		f1_a,
		precision_b,
		recall_b,
		f1_b,
		(kind_a + kind_b) / 2,
	)


def main() -> int:
	cases = [
		cast(dict[str, object], json.loads(line))
		for line in DATASET_PATH.read_text().splitlines()
		if line.strip()
	]
	results = [evaluate_case(case) for case in cases]
	count = len(results)
	aggregate_f1 = (
		sum(min(result.f1_a, result.f1_b) for result in results) / count if count else 0.0
	)
	aggregate_kind = sum(result.kind_accuracy for result in results) / count if count else 0.0

	agreements = []
	for case in cases:
		annotations = cast(dict[str, object], case["annotations"])
		labels_a = cast(list[dict[str, object]], annotations["annotatorA"])
		labels_b = cast(list[dict[str, object]], annotations["annotatorB"])
		pairs = greedy_match(
			[str(label["text"]) for label in labels_a],
			[str(label["text"]) for label in labels_b],
		)
		_, _, agreement = prf(len(pairs), len(labels_a), len(labels_b))
		agreements.append(agreement)
	aggregate_agreement = sum(agreements) / count if count else 0.0

	print(
		f"\nDataset size: {count} double-annotated cases\n"
		f"Worst-annotator F1: {aggregate_f1:.3f} (threshold {THRESHOLDS['min_f1_vs_annotator']})\n"
		f"Kind accuracy: {aggregate_kind:.3f} "
		f"(threshold {THRESHOLDS['min_kind_accuracy']})\n"
		f"Inter-annotator F1: {aggregate_agreement:.3f} "
		f"(threshold {THRESHOLDS['min_inter_annotator_f1']})"
	)
	failures = []
	if aggregate_f1 < THRESHOLDS["min_f1_vs_annotator"]:
		failures.append("worst-annotator F1")
	if aggregate_kind < THRESHOLDS["min_kind_accuracy"]:
		failures.append("kind accuracy")
	if aggregate_agreement < THRESHOLDS["min_inter_annotator_f1"]:
		failures.append("inter-annotator agreement")
	if failures:
		print(f"RELEASE GATE FAILED: {'; '.join(failures)} below threshold")
		return 1
	print("Release thresholds met")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
