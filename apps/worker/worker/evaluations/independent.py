from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from ..documents.normalizer import SKILL_ALIASES


def independent_report(
	normalized_facts: Mapping[str, object], job_description: str | None
) -> tuple[int, list[dict[str, object]]]:
	contact = normalized_facts.get("contact")
	contact_facts: Mapping[str, object] = (
		cast(Mapping[str, object], contact) if isinstance(contact, Mapping) else {}
	)
	skills = normalized_facts.get("skills")
	recognized_skills: list[Mapping[str, object]] = [
		cast(Mapping[str, object], item)
		for item in cast(list[object], skills)
		if isinstance(item, Mapping)
	] if isinstance(skills, list) else []
	documented_skill_names = {str(item.get("canonicalName")) for item in recognized_skills}
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
	if not recognized_skills:
		suggestions.append(
			{
				"title": "Make skills easier to verify",
				"detail": "Name the tools and technologies you used in your experience.",
			}
		)
	if job_description:
		missing = [
			skill
			for skill, aliases in SKILL_ALIASES.items()
			if any(alias in job_description.casefold() for alias in aliases)
			and skill not in documented_skill_names
		]
		if missing:
			suggestions.append(
				{
					"title": "Review role-specific evidence",
					"detail": (
						f"The job description mentions {', '.join(missing)}. Add it only "
						"when your resume already supports the claim."
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
		+ min(40, len(recognized_skills) * 8),
	)
	return score, suggestions
