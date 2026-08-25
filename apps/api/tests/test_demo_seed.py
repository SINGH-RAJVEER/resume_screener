from datetime import UTC, datetime
from typing import cast

from app.demo.seed import (
    CANDIDATES,
    REQUIREMENTS,
    build_demo_world,
    eligibility_for_candidate,
    score_from_outcomes,
)

NOW = datetime.now(UTC)


def world():
    return build_demo_world(NOW)


def test_every_candidate_has_outcomes_for_all_scored_requirements() -> None:
    for spec in CANDIDATES:
        missing = [
            requirement.stable_id
            for requirement in REQUIREMENTS
            if requirement.kind != "ignored" and requirement.stable_id not in spec.outcomes
        ]
        assert missing == [], spec.key


def test_scores_match_the_scoring_policy() -> None:
    outcomes = {
        stable_id: outcome for stable_id, (outcome, _reason) in CANDIDATES[0].outcomes.items()
    }
    # Priya: met(2) + partial(1) + met(2) across non-gate weight 5.
    assert score_from_outcomes(outcomes) == round(100 * 4.5 / 5)
    all_unknown = {stable_id: "unknown" for stable_id in outcomes}
    assert score_from_outcomes(all_unknown) is None


def test_eligibility_follows_hard_gates_only() -> None:
    by_key = {spec.key: spec for spec in CANDIDATES}
    # Tom's degree gate fails outright.
    assert eligibility_for_candidate(by_key["tom-becker"]) == "not_eligible"
    # Ana's degree gate is unknown, which requires review instead of a pass.
    assert eligibility_for_candidate(by_key["ana-reyes"]) == "needs_review"
    # Priya satisfies every gate.
    assert eligibility_for_candidate(by_key["priya-sharma"]) == "eligible"


def test_world_references_are_internally_consistent() -> None:
    w = world()
    requirement_ids = {requirement.id for requirement in w.requirements}
    version_ids = {version.id for version in w.versions}
    submission_ids = {submission.id for submission in w.submissions}

    assert all(a.job_requirement_id in requirement_ids for a in w.assessments)
    assert all(e.resume_version_id in version_ids for e in w.evaluations)
    assert all(e.resume_submission_id in submission_ids for e in w.evaluations)
    batch_submissions = {
        (s.batch_evaluation_id, s.resume_submission_id) for s in w.batch_submissions
    }
    for evaluation in w.evaluations:
        key = (evaluation.batch_evaluation_id, evaluation.resume_submission_id)
        assert key in batch_submissions


def test_ranks_cover_exactly_the_eligible_evaluations() -> None:
    w = world()
    eligible = [e for e in w.evaluations if e.eligibility == "eligible"]
    ranks = sorted(int(rank) for rank in (e.rank for e in eligible) if rank is not None)
    assert ranks == list(range(1, len(eligible) + 1))
    assert all(e.rank is None for e in w.evaluations if e.eligibility != "eligible")
    scores = [int(e.score) for e in eligible if e.score is not None]
    assert scores == sorted(scores, reverse=True)


def test_assessment_evidence_quotes_stored_resume_blocks() -> None:
    w = world()
    blocks_by_version: dict[str, dict[str, str]] = {}
    for version in w.versions:
        artifact = version.extraction_blocks or {}
        texts: dict[str, str] = {}
        candidate_blocks = cast("list[object]", artifact.get("blocks", []))
        for block in candidate_blocks:
            if not isinstance(block, dict):
                continue
            entry = cast("dict[str, object]", block)
            texts[str(entry.get("id"))] = str(entry.get("text"))
        blocks_by_version[version.id] = texts
    submissions = {s.id: s.resume_version_id for s in w.submissions}

    for assessment in w.assessments:
        evaluation = next(e for e in w.evaluations if e.id == assessment.evaluation_id)
        stored_texts = blocks_by_version[submissions[evaluation.resume_submission_id]]
        for entry in assessment.evidence:
            block_id = str(entry["blockId"])
            assert block_id in stored_texts
            assert entry["quote"] == stored_texts[block_id]


def test_processing_evaluation_carries_no_result() -> None:
    w = world()
    processing = [e for e in w.evaluations if e.status == "processing"]
    assert len(processing) == 1
    assert processing[0].score is None
    assert processing[0].eligibility == "pending"


def test_demo_retention_outlives_any_tour() -> None:
    w = world()
    horizon = NOW.replace(year=NOW.year + 1) if NOW.year < 2261 else NOW
    assert all(d.retention_date > horizon for d in w.documents)
    assert all(e.retention_date > horizon for e in w.independent_evaluations)
