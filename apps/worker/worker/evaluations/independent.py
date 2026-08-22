from collections.abc import Mapping
from typing import cast

from ..documents.vocabulary import mentioned_skills

MAX_LISTED_GAPS = 8


def independent_report(
	normalized_facts: Mapping[str, object], job_description: str | None
) -> tuple[int, list[dict[str, object]]]:
	contact = cast(Mapping[str, object], normalized_facts.get("contact") or {})
	skills = documented_skill_names(normalized_facts)
	suggestions = readiness_suggestions(contact, skills, normalized_facts)
	if job_description:
		suggestions.extend(role_alignment_suggestions(job_description, skills))
	score = readiness_score(contact, skills, normalized_facts)
	return score, suggestions


def readiness_suggestions(
	contact: Mapping[str, object],
	documented_skill_names: set[str],
	facts: Mapping[str, object],
) -> list[dict[str, object]]:
	suggestions: list[dict[str, object]] = []
	if not contact.get("name"):
		suggestions.append(
			{"title": "Add a clear name", "detail": "Start the resume with your name."}
		)
	if not contact.get("email"):
		suggestions.append(
			{
				"title": "Add contact details",
				"detail": "Include a professional email address.",
			}
		)
	if not documented_skill_names:
		suggestions.append(
			{
				"title": "Make skills easier to verify",
				"detail": "Name the tools and technologies you used in your experience.",
			}
		)
	if not _entries(facts.get("employment")):
		suggestions.append(
			{
				"title": "Document your experience",
				"detail": (
					"List each role with the employer, title, and dates so your "
					"experience can be verified."
				),
			}
		)
	if not _entries(facts.get("education")) and not _entries(facts.get("certifications")):
		suggestions.append(
			{
				"title": "Add education or certifications",
				"detail": (
					"Include degrees or credentials with their issuing "
					"institutions and dates."
				),
			}
		)
	return suggestions


def role_alignment_suggestions(
	job_description: str, documented_skill_names: set[str]
) -> list[dict[str, object]]:
	missing = sorted(mentioned_skills(job_description) - documented_skill_names)
	if not missing:
		return [
			{
				"title": "Connect experience to the role",
				"detail": (
					"Use specific outcomes to show how your documented skills "
					"apply to this role."
				),
			}
		]
	return [
		{
			"title": "Review role-specific evidence",
			"detail": (
				f"The job description mentions {', '.join(missing[:MAX_LISTED_GAPS])}. "
				"Add them only when your resume already supports the claim."
			),
		}
	]


def readiness_score(
	contact: Mapping[str, object],
	skills: set[str],
	facts: Mapping[str, object],
) -> int:
	return min(
		100,
		20
		+ (15 if contact.get("name") else 0)
		+ (15 if contact.get("email") else 0)
		+ (10 if contact.get("location") else 0)
		+ min(25, len(skills) * 5)
		+ (5 if _entries(facts.get("employment")) else 0)
		+ (3 if _entries(facts.get("education")) else 0)
		+ (2 if _entries(facts.get("certifications")) else 0),
	)


def documented_skill_names(facts: Mapping[str, object]) -> set[str]:
	names: set[str] = set()
	for item in _entries(facts.get("skills")):
		if item.get("canonicalName"):
			names.add(str(item["canonicalName"]))
	return names


def _entries(value: object) -> list[Mapping[str, object]]:
	if not isinstance(value, list):
		return []
	return [
		cast(Mapping[str, object], item)
		for item in cast(list[object], value)
		if isinstance(item, Mapping)
	]
