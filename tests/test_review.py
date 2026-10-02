import sqlite3

import pytest

from pitchkitchen.ideas.store import create_idea, ensure_schema as ensure_ideas
from pitchkitchen.review.jev import JevUnavailable, parse_answers
from pitchkitchen.review.logic import decide, over_budget
from pitchkitchen.review.store import ensure_schema as ensure_review
from pitchkitchen.review.store import forget, jev_calls_used, record_verdict

from fakes import jev_scores


def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    ensure_ideas(db)
    ensure_review(db)
    return db


sample_answers = jev_scores


def test_safety_above_cutoff_forces_kill():
    assert decide(3, 3, 3, 0.51, 0.95) == ("KILL", "safety_veto")
    assert decide(3, 3, 3, 0.5, 0.95)[0] == "SHIP"


def test_an_average_under_one_point_two_is_kill():
    assert decide(1.1, 1.1, 0.8, 0.1, 0.9) == ("KILL", "all_weak")
    assert decide(1.2, 1.2, 1.2, 0.1, 0.9) == ("FIX", "below_cutoff")


def test_a_score_under_two_is_fix():
    assert decide(2.4, 2.1, 1.9, 0.1, 0.9) == ("FIX", "below_cutoff")


def test_low_confidence_does_not_ship():
    assert decide(2.5, 2.5, 2.5, 0.1, 0.59) == ("FIX", "low_confidence")


def test_clear_scores_ship():
    assert decide(2.0, 2.0, 2.0, 0.5, 0.6) == ("SHIP", "all_clear")


def test_parse_answers_reads_the_jev_payload():
    measured = parse_answers(sample_answers(2.2, 2.0, 2.5, 0.2, 0.8))
    assert measured["market_need"] == 2.2
    assert measured["confidence"] == 0.8
    assert measured["safety_risk"] == 0.2


def test_confidence_is_the_chance_each_score_is_solid_or_better():
    payload = sample_answers(2.9, 2.8, 2.2, 0.03)
    payload["answers"]["differentiation"]["confidence"] = 0.58
    payload["answers"]["differentiation"]["probabilities"] = {"0": 0.0, "1": 0.09, "2": 0.59, "3": 0.32}

    assert parse_answers(payload)["confidence"] == pytest.approx(0.9)


def test_parse_answers_rejects_a_broken_payload():
    with pytest.raises(JevUnavailable):
        parse_answers({"answers": {}})


TEXT = {"one_liner": "We help X", "story": "Story", "answers": ["First"]}


def pitch_id(db):
    return create_idea(db, "Ada", "We help X", "Story", now="2026-09-29T10:00:00Z")["branch"][0]["id"]


def test_missing_key_stores_pending_and_skips_jev():
    db = connection()
    calls = []

    def transport(body, api_key):
        calls.append(api_key)
        return {}

    verdict = record_verdict(
        db,
        pitch_id(db),
        TEXT,
        "",
        now="2026-09-29T10:00:01Z",
        transport=transport,
    )

    assert calls == []
    assert verdict["label"] == "PENDING"
    assert verdict["rule"] == "missing_key"


def test_record_verdict_sends_the_founder_text_and_stores_the_rule():
    db = connection()

    def transport(body, api_key):
        assert body["state"] == TEXT
        assert api_key == "test-key"
        return sample_answers(1.2, 2.5, 2.5, 0.1)

    verdict = record_verdict(db, pitch_id(db), TEXT, "test-key", transport=transport)

    assert verdict["label"] == "FIX"
    assert verdict["rule"] == "below_cutoff"
    assert verdict["market_need"] == 1.2


def test_a_failed_call_is_pending_and_a_retry_replaces_it():
    db = connection()
    revision_id = pitch_id(db)

    def broken(body, api_key):
        return {"answers": {}}

    def ship(body, api_key):
        return sample_answers(3, 3, 3, 0.0)

    first = record_verdict(db, revision_id, TEXT, "test-key", transport=broken)
    second = record_verdict(db, revision_id, TEXT, "test-key", transport=ship)

    assert first["rule"] == "request_failed"
    assert second["label"] == "SHIP"


def test_a_final_verdict_is_not_replaced():
    db = connection()
    revision_id = pitch_id(db)

    def ship(body, api_key):
        return sample_answers(3, 3, 3, 0.0)

    def kill(body, api_key):
        return sample_answers(3, 3, 3, 0.9)

    first = record_verdict(db, revision_id, TEXT, "test-key", transport=ship)
    second = record_verdict(db, revision_id, TEXT, "test-key", transport=kill)

    assert first["label"] == "SHIP"
    assert second["label"] == "SHIP"
    assert second["id"] == first["id"]


def test_over_budget_only_when_the_budget_is_used_up():
    assert not over_budget(9, 10)
    assert over_budget(10, 10)
    assert not over_budget(500, None)


def test_every_jev_call_is_logged_including_failures():
    db = connection()
    revision_id = pitch_id(db)

    def broken(body, api_key):
        return {"answers": {}}

    def ship(body, api_key):
        return sample_answers(3, 3, 3, 0.0)

    record_verdict(db, revision_id, TEXT, "test-key", transport=broken, idea_id=1, budget=10)
    record_verdict(db, revision_id, TEXT, "test-key", transport=ship, idea_id=1, budget=10)
    record_verdict(db, revision_id, TEXT, "test-key", transport=ship, idea_id=1, budget=10)

    oks = [row["ok"] for row in db.execute("SELECT ok FROM jev_calls ORDER BY id")]
    assert oks == [0, 1]
    assert jev_calls_used(db, 1) == 2
    assert jev_calls_used(db, 2) == 0


def test_a_spent_budget_is_pending_and_skips_jev():
    db = connection()
    revision_id = pitch_id(db)
    calls = []

    def broken(body, api_key):
        calls.append(body)
        return {"answers": {}}

    record_verdict(db, revision_id, TEXT, "test-key", transport=broken, idea_id=1, budget=1)
    verdict = record_verdict(db, revision_id, TEXT, "test-key", transport=broken, idea_id=1, budget=1)

    assert len(calls) == 1
    assert verdict["label"] == "PENDING"
    assert verdict["rule"] == "over_budget"
    assert "JEV_BUDGET_PER_IDEA" in verdict["explanation"]


def test_a_missing_key_is_not_logged_as_a_call():
    db = connection()
    record_verdict(db, pitch_id(db), TEXT, "", idea_id=1, budget=10)
    assert jev_calls_used(db, 1) == 0


def test_forget_removes_the_call_log_with_the_verdicts():
    db = connection()
    revision_id = pitch_id(db)

    def ship(body, api_key):
        return sample_answers(3, 3, 3, 0.0)

    record_verdict(db, revision_id, TEXT, "test-key", transport=ship, idea_id=1, budget=10)
    forget(db, [revision_id])

    assert jev_calls_used(db, 1) == 0
