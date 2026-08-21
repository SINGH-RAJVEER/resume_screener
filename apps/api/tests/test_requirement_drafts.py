from app.requirement_drafts import draft_requirements


def test_drafts_unique_bullet_lines_with_stable_ids() -> None:
	drafts = draft_requirements("- Python experience\n* PostgreSQL experience\n- Python experience")

	assert [draft["normalizedText"] for draft in drafts] == [
		"Python experience",
		"PostgreSQL experience",
	]
	assert all(draft["stableId"].startswith("draft-") for draft in drafts)
