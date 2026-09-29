import sqlite3

import pytest

from pitchgate.ideas.store import create_idea, ensure_schema as ensure_ideas
from pitchgate.verdicts.jev import JevUnavailable, parse_answers
from pitchgate.verdicts.logic import decide
from pitchgate.verdicts.store import ensure_schema as ensure_verdicts
from pitchgate.verdicts.store import record_verdict


def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    ensure_ideas(db)
    ensure_verdicts(db)
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


def test_missing_key_stores_pending_and_skips_jev():
    db = connection()
    idea = create_idea(db, "Ada", "Problem", "Students", "An app", now="2026-09-28T10:00:00Z")
    calls = []

    def transport(body, api_key):
        calls.append(api_key)
        return {}

    verdict = record_verdict(
        db,
        idea["revisions"][0],
        "",
        now="2026-09-28T10:00:01Z",
        transport=transport,
    )

    assert calls == []
    assert verdict["label"] == "PENDING"
    assert verdict["rule"] == "missing_key"


def test_record_verdict_stores_the_rule_that_fired():
    db = connection()
    idea = create_idea(db, "Ada", "Problem", "Students", "An app", now="2026-09-28T10:00:00Z")

    def transport(body, api_key):
        assert body["state"]["problem"] == "Problem"
        assert api_key == "test-key"
        return sample_answers(1.2, 2.5, 2.5, 0.1)

    verdict = record_verdict(
        db,
        idea["revisions"][0],
        "test-key",
        transport=transport,
    )

    assert verdict["label"] == "FIX"
    assert verdict["rule"] == "below_cutoff"
    assert verdict["market_need"] == 1.2


def test_a_final_verdict_is_not_replaced():
    db = connection()
    idea = create_idea(db, "Ada", "Problem", "Students", "An app", now="2026-09-28T10:00:00Z")
    revision = idea["revisions"][0]

    def ship(body, api_key):
        return sample_answers(3, 3, 3, 0.0)

    def kill(body, api_key):
        return sample_answers(3, 3, 3, 0.9)

    first = record_verdict(db, revision, "test-key", transport=ship)
    second = record_verdict(db, revision, "test-key", transport=kill)

    assert first["label"] == "SHIP"
    assert second["label"] == "SHIP"
    assert second["id"] == first["id"]
