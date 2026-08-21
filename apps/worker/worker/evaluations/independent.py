
from collections.abc import Mapping
from typing import cast

from ..documents.vocabulary import mentioned_skills

MAX_LISTED_GAPS = 8


def independent_report(
	normalized_facts: Mapping[str, object], job_description: str | None
) -> tuple[int, list[dict[str, object]]]:
	contact = normalized_facts.get("contact")
	contact_facts: Mapping[str, object] = (
		cast(Mapping[str, object], contact) if isinstance(contact, Mapping) else {}
	)
	skills = normalized_facts.get("skills")
	documented_skill_names: set[str] = {
		str(item.get("canonicalName"))
		for item in (
			cast(Mapping[str, object], entry)
			for entry in cast(list[object], skills)
			if isinstance(entry, Mapping)
		)
	} if isinstance(skills, list) else set()
	suggestions: list[dict[str, object]] = []
	if not contact_facts.get("name"):
		suggestions.append(
			{"title": "Add a clear name", "detail": "Start the resume with your name."}
		)
	if not contact_facts.get("email"):
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
	if job_description:
		missing = sorted(mentioned_skills(job_description) - documented_skill_names)
		if missing:
			suggestions.append(
				{
					"title": "Review role-specific evidence",
					"detail": (
						f"The job description mentions {', '.join(missing[:MAX_LISTED_GAPS])}. "
						"Add them only when your resume already supports the claim."
					),
				}
			)
		else:
			suggestions.append(
				{
					"title": "Connect experience to the role",
					"detail": (
						"Use specific outcomes to show how your documented skills "
						"apply to this role."
					),
				}
			)
	score = min(
		100,
		20
		+ (20 if contact_facts.get("name") else 0)
		+ (20 if contact_facts.get("email") else 0)
		+ min(40, len(documented_skill_names) * 8),
	)
	return score, suggestions
