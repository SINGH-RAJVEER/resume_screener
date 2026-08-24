"""Measure the unsupported-claim rate of extraction artifacts.

Each case is a pair of JSON files in one directory: `<name>.blocks.json`
holding the extraction-blocks artifact and `<name>.extraction.json` holding
the structured model extraction. The script reports overall and
per-collection rates and exits nonzero when `--max-rate` is exceeded. Use
it over exported evaluation-set artifacts before changing prompts, schemas,
or models.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker.extraction.claims import ClaimReport, measure_unsupported_claims


def block_texts(blocks_artifact: object) -> dict[str, str]:
	if not isinstance(blocks_artifact, dict):
		return {}
	raw_blocks = blocks_artifact.get("blocks")
	if not isinstance(raw_blocks, list):
		return {}
	return {
		str(block["id"]): str(block.get("text", ""))
		for block in raw_blocks
		if isinstance(block, dict) and block.get("id")
	}


def case_paths(directory: Path) -> list[tuple[str, Path, Path]]:
	cases: list[tuple[str, Path, Path]] = []
	for extraction_path in sorted(directory.glob("*.extraction.json")):
		name = extraction_path.name.removesuffix(".extraction.json")
		blocks_path = directory / f"{name}.blocks.json"
		if blocks_path.is_file():
			cases.append((name, extraction_path, blocks_path))
	return cases


def report_for(extraction: object, blocks: object) -> ClaimReport:
	return measure_unsupported_claims(
		extraction if isinstance(extraction, dict) else {},
		block_texts(blocks),
	)


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("directory", type=Path)
	parser.add_argument(
		"--max-rate", type=float, default=None,
		help="Fail when the unsupported-claim rate exceeds this fraction",
	)
	arguments = parser.parse_args()
	cases = case_paths(arguments.directory)
	if not cases:
		print(f"No <name>.blocks.json / .extraction.json pairs in {arguments.directory}")
		return 1
	total_claims = 0
	unsupported = 0
	worst: tuple[float, str] | None = None
	for name, extraction_path, blocks_path in cases:
		report = report_for(
			json.loads(extraction_path.read_text()),
			json.loads(blocks_path.read_text()),
		)
		rate = report.rate
		assert rate is not None
		print(
			f"{name}: {report.unsupported_claims}/{report.total_claims} "
			f"unsupported ({rate:.1%}) "
			+ " ".join(
				f"{collection}={item.invalid_citations + item.ungrounded_values}/{item.total}"
				for collection, item in report.collections.items()
			)
		)
		for example in report.examples:
			print(f"  {example}")
		total_claims += report.total_claims
		unsupported += report.unsupported_claims
		if worst is None or rate > worst[0]:
			worst = (rate, name)
	if not total_claims:
		print("No claims found in the supplied artifacts")
		return 1
	overall = unsupported / total_claims
	print(
		f"\nOverall: {unsupported}/{total_claims} unsupported ({overall:.1%}); "
		f"worst case {worst[1]} at {worst[0]:.1%}"
	)
	if arguments.max_rate is not None and overall > arguments.max_rate:
		print(f"FAILED: rate exceeds --max-rate {arguments.max_rate:.1%}")
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
