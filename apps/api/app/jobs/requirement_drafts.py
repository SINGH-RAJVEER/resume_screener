from hashlib import blake2b

MAX_DRAFT_REQUIREMENTS = 20


def draft_requirements(description: str) -> list[dict[str, str]]:
	unique_lines: set[str] = set()
	drafts: list[dict[str, str]] = []
	for line in description.splitlines():
		normalized = " ".join(line.removeprefix("-").removeprefix("*").split())
		if len(normalized) < 3 or normalized.casefold() in unique_lines:
			continue
		unique_lines.add(normalized.casefold())
		drafts.append(
			{
				"stableId": f"draft-{blake2b(normalized.encode(), digest_size=6).hexdigest()}",
				"normalizedText": normalized,
			}
		)
		if len(drafts) == MAX_DRAFT_REQUIREMENTS:
			break
	return drafts
