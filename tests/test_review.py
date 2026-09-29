import sqlite3

import pytest

from pitchkitchen.ideas.store import create_idea, ensure_schema as ensure_ideas
from pitchkitchen.review.jev import JevUnavailable, parse_answers
from pitchkitchen.review.logic import decide
from pitchkitchen.review.store import ensure_schema as ensure_review
from pitchkitchen.review.store import record_verdict


def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    ensure_ideas(db)
    ensure_review(db)
    return db


def sample_answers(market, feasibility, differentiation, safety, confidence=0.9):
    def score(value):
        return {"type": "score", "score": value, "confidence": confidence}

    return {
        "answers": {
            "market_need": score(market),
            "feasibility": score(feasibility),
            "differentiation": score(differentiation),
            "safety_risk": {"type": "noul", "noul": safety},
        }
    }


def test_safety_above_cutoff_forces_kill():
    assert decide(3, 3, 3, 0.51, 0.95) == ("KILL", "safety_veto")
    assert decide(3, 3, 3, 0.5, 0.95)[0] == "SHIP"


def test_a_score_under_two_is_fix():
    assert decide(2.4, 2.1, 1.9, 0.1, 0.9) == ("FIX", "below_cutoff")


def test_low_confidence_does_not_ship():
    assert decide(2.5, 2.5, 2.5, 0.1, 0.59) == ("FIX", "low_confidence")


def test_clear_scores_ship():
    assert decide(2.0, 2.0, 2.0, 0.5, 0.6) == ("SHIP", "all_clear")


def test_parse_answers_reads_the_jev_payload():
    measured = parse_answers(sample_answers(2.2, 1.0, 2.5, 0.2, 0.8))
    assert measured["market_need"] == 2.2
    assert measured["confidence"] == 0.8
    assert measured["safety_risk"] == 0.2


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
