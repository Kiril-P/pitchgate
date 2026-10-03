import sqlite3

import pytest

from pitchkitchen.ideas.store import create_idea, ensure_schema as ensure_ideas
from pitchkitchen.review.jev import JevUnavailable, judge, parse_answers, parse_tasting
from pitchkitchen.review.logic import band, can_serve, decide, decide_tasting, gate_ready, over_budget
from pitchkitchen.review.store import ensure_schema as ensure_review
from pitchkitchen.review.store import forget, gates_for, gates_passed, jev_calls_used, record_gate, record_verdict

from fakes import jev_scores, tasting_scores


def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    ensure_ideas(db)
    ensure_review(db)
    return db


def test_safety_above_cutoff_is_unproven():
    assert decide(3, 3, 3, 0.51, 0.95) == ("UNPROVEN", "safety_veto")
    assert decide(3, 3, 3, 0.5, 0.95)[0] == "PROVEN"


def test_an_average_under_one_point_two_is_unproven():
    assert decide(1.1, 1.1, 0.8, 0.1, 0.9) == ("UNPROVEN", "all_weak")
    assert decide(1.2, 1.2, 1.2, 0.1, 0.9) == ("PARTIAL", "below_cutoff")


def test_a_dodged_question_is_partial_even_with_strong_scores():
    assert decide(3, 3, 3, 0.0, 0.95, evidence=3, answered=0.2) == ("PARTIAL", "dodged")
    assert decide(3, 3, 3, 0.0, 0.95, evidence=3, answered=0.5)[0] == "PROVEN"


def test_the_pitch_is_not_checked_for_answering_a_question():
    assert decide(3, 3, 3, 0.0, 0.95, evidence=3, answered=None)[0] == "PROVEN"


def test_a_score_under_two_is_partial():
    assert decide(2.4, 2.1, 1.9, 0.1, 0.9) == ("PARTIAL", "below_cutoff")


def test_claims_without_facts_are_not_proven():
    assert decide(2.5, 2.5, 2.5, 0.0, 0.9, evidence=1.9) == ("PARTIAL", "mostly_claims")


def test_low_confidence_is_not_proven():
    assert decide(2.5, 2.5, 2.5, 0.1, 0.59) == ("PARTIAL", "low_confidence")


def test_clear_scores_are_proven():
    assert decide(2.0, 2.0, 2.0, 0.5, 0.6, evidence=2.0, answered=0.9) == ("PROVEN", "all_clear")


def test_bands_replace_decimals():
    assert [band(s) for s in (None, 0.2, 1.4, 2.0, 2.6)] == ["", "None", "Weak", "Solid", "Strong"]


def test_the_tasting_gate_rules():
    assert decide_tasting(3, 3, 3, 0.9) == ("SENT_BACK", "gate_safety")
    assert decide_tasting(1.9, 3, 3, 0.0) == ("SENT_BACK", "gate_weak_evidence")
    assert decide_tasting(2.0, 1.0, 1.0, 0.0) == ("SENT_BACK", "gate_weak_signal")
    assert decide_tasting(2.0, 1.5, 1.0, 0.0) == ("PASSED", "gate_clear")


def test_the_gate_needs_three_logs_and_something_new():
    assert not gate_ready(2, 2)
    assert not gate_ready(3, 0)
    assert gate_ready(3, 1)


def test_serving_needs_proven_and_three_logs():
    assert can_serve("PROVEN", 3)
    assert not can_serve("PROVEN", 2)
    assert not can_serve("PARTIAL", 5)


def test_parse_answers_reads_the_jev_payload():
    measured = parse_answers(jev_scores(2.2, 2.0, 2.5, 0.2, 0.8, evidence=1.0, answered=0.3), with_answered=True)
    assert measured["market_need"] == 2.2
    assert measured["confidence"] == 0.8
    assert measured["safety_risk"] == 0.2
    assert measured["evidence"] == 1.0
    assert measured["answered"] == 0.3
    assert parse_answers(jev_scores(2, 2, 2, 0))["answered"] is None


def test_confidence_is_the_chance_each_score_is_solid_or_better():
    payload = jev_scores(2.9, 2.8, 2.2, 0.03)
    payload["answers"]["differentiation"]["probabilities"] = {"0": 0.0, "1": 0.09, "2": 0.59, "3": 0.32}
    assert parse_answers(payload)["confidence"] == pytest.approx(0.9)


def test_broken_payloads_are_rejected():
    with pytest.raises(JevUnavailable):
        parse_answers({"answers": {}})
    with pytest.raises(JevUnavailable):
        parse_tasting({"answers": {"evidence_strength": {}}})


def test_judge_asks_answered_only_when_chef_asked_something():
    bodies = []

    def transport(body, api_key):
        bodies.append(body)
        return jev_scores(2, 2, 2, 0)

    judge({"one_liner": "x", "latest_question": ""}, "key", transport=transport)
    judge({"one_liner": "x", "latest_question": "Who paid?"}, "key", transport=transport)

    assert "answered" not in bodies[0]["questions"]
    assert "answered" in bodies[1]["questions"]
    assert "evidence" in bodies[0]["questions"]


TEXT = {"one_liner": "We help X", "story": "Story", "answers": ["First"], "evidence": []}


def pitch_id(db):
    return create_idea(db, "Ada", "We help X", "Story", now="2026-09-29T10:00:00Z")["branch"][0]["id"]


def test_missing_key_stores_pending_and_skips_jev():
    db = connection()
    calls = []

    def transport(body, api_key):
        calls.append(api_key)
        return {}

    verdict = record_verdict(db, pitch_id(db), TEXT, "", now="2026-09-29T10:00:01Z", transport=transport)

    assert calls == []
    assert verdict["label"] == "PENDING"
    assert verdict["rule"] == "missing_key"


def test_record_verdict_stores_the_rule_and_bands():
    db = connection()

    def transport(body, api_key):
        assert body["state"] == TEXT
        assert api_key == "test-key"
        return jev_scores(1.2, 2.5, 2.5, 0.1)

    verdict = record_verdict(db, pitch_id(db), TEXT, "test-key", transport=transport)

    assert verdict["label"] == "PARTIAL"
    assert verdict["rule"] == "below_cutoff"
    assert verdict["market_need_band"] == "Weak"
    assert verdict["evidence_band"] == "Strong"


def test_a_failed_call_is_pending_and_a_retry_replaces_it():
    db = connection()
    revision_id = pitch_id(db)

    first = record_verdict(db, revision_id, TEXT, "test-key", transport=lambda body, key: {"answers": {}})
    second = record_verdict(db, revision_id, TEXT, "test-key", transport=lambda body, key: jev_scores(3, 3, 3, 0.0))

    assert first["rule"] == "request_failed"
    assert second["label"] == "PROVEN"


def test_a_final_verdict_is_not_replaced():
    db = connection()
    revision_id = pitch_id(db)

    first = record_verdict(db, revision_id, TEXT, "test-key", transport=lambda body, key: jev_scores(3, 3, 3, 0.0))
    second = record_verdict(db, revision_id, TEXT, "test-key", transport=lambda body, key: jev_scores(3, 3, 3, 0.9))

    assert first["label"] == second["label"] == "PROVEN"
    assert second["id"] == first["id"]


def test_over_budget_only_when_the_budget_is_used_up():
    assert not over_budget(9, 10)
    assert over_budget(10, 10)
    assert not over_budget(500, None)


def test_only_successful_calls_count_toward_the_budget():
    db = connection()
    revision_id = pitch_id(db)

    record_verdict(db, revision_id, TEXT, "test-key", transport=lambda b, k: {"answers": {}}, idea_id=1, budget=10)
    record_verdict(db, revision_id, TEXT, "test-key", transport=lambda b, k: jev_scores(3, 3, 3, 0), idea_id=1, budget=10)

    oks = [row["ok"] for row in db.execute("SELECT ok FROM jev_calls ORDER BY id")]
    assert oks == [0, 1]
    assert jev_calls_used(db, 1) == 1
    assert jev_calls_used(db, 2) == 0


def test_three_failures_on_one_text_stop_retrying():
    db = connection()
    revision_id = pitch_id(db)
    calls = []

    def broken(body, api_key):
        calls.append(body)
        return {"answers": {}}

    for _ in range(4):
        verdict = record_verdict(db, revision_id, TEXT, "test-key", transport=broken, idea_id=1, budget=10)

    assert len(calls) == 3
    assert verdict["rule"] == "retry_cap"


def test_a_spent_budget_is_pending_and_skips_jev():
    db = connection()
    first, second = pitch_id(db), pitch_id(db)
    calls = []

    def proven(body, api_key):
        calls.append(body)
        return jev_scores(3, 3, 3, 0)

    record_verdict(db, first, TEXT, "test-key", transport=proven, idea_id=1, budget=1)
    verdict = record_verdict(db, second, TEXT, "test-key", transport=proven, idea_id=1, budget=1)

    assert len(calls) == 1
    assert verdict["rule"] == "over_budget"
    assert "JEV_BUDGET_PER_IDEA" in verdict["explanation"]


def test_record_gate_scores_and_stores_each_attempt():
    db = connection()
    revision_id = pitch_id(db)

    sent_back = record_gate(db, 1, revision_id, 1, 3, {}, "key", transport=lambda b, k: tasting_scores(1, 2, 2))
    passed = record_gate(db, 1, revision_id, 1, 4, {}, "key", transport=lambda b, k: tasting_scores(2.5, 2, 2))

    assert sent_back["label"] == "SENT_BACK"
    assert passed["label"] == "PASSED"
    assert passed["evidence_strength_band"] == "Strong"
    assert gates_passed(db, 1) == 1
    assert [g["purpose"] for g in db.execute("SELECT purpose FROM jev_calls")] == ["gate", "gate"]


def test_a_gate_without_key_budget_or_answer_is_pending():
    db = connection()
    revision_id = pitch_id(db)

    assert record_gate(db, 1, revision_id, 1, 3, {}, "")["rule"] == "missing_key"
    assert record_gate(db, 1, revision_id, 1, 3, {}, "key", transport=lambda b, k: {})["rule"] == "request_failed"
    record_gate(db, 1, revision_id, 1, 3, {}, "key", transport=lambda b, k: tasting_scores(3, 3, 3))
    assert record_gate(db, 1, revision_id, 1, 3, {}, "key", budget=1)["rule"] == "over_budget"
    assert gates_passed(db, 1) == 1


def test_forget_removes_gates_calls_and_verdicts():
    db = connection()
    revision_id = pitch_id(db)
    record_verdict(db, revision_id, TEXT, "key", transport=lambda b, k: jev_scores(3, 3, 3, 0), idea_id=1, budget=10)
    record_gate(db, 1, revision_id, 1, 3, {}, "key", transport=lambda b, k: tasting_scores(3, 3, 3))

    forget(db, 1, [revision_id])

    assert jev_calls_used(db, 1) == 0
    assert gates_for(db, 1) == []


def test_an_old_database_gets_new_labels_and_chef_kinds():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    ensure_ideas(db)
    db.executescript(
        """
        CREATE TABLE verdicts (id INTEGER PRIMARY KEY, revision_id INTEGER NOT NULL UNIQUE, market_need REAL,
            feasibility REAL, differentiation REAL, safety_risk REAL, confidence REAL, label TEXT NOT NULL,
            rule TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE chef_messages (id INTEGER PRIMARY KEY, revision_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('turn', 'polished')), body TEXT NOT NULL,
            question TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, UNIQUE (revision_id, kind));
        INSERT INTO verdicts (revision_id, label, rule, created_at) VALUES (1, 'SHIP', 'all_clear', 'now');
        INSERT INTO verdicts (revision_id, label, rule, created_at) VALUES (2, 'KILL', 'all_weak', 'now');
        INSERT INTO chef_messages (revision_id, kind, body, created_at) VALUES (1, 'turn', 'Old roast', 'now');
        """
    )

    ensure_review(db)

    assert [r["label"] for r in db.execute("SELECT label FROM verdicts ORDER BY id")] == ["PROVEN", "UNPROVEN"]
    db.execute("INSERT INTO chef_messages (revision_id, kind, body, created_at) VALUES (1, 'homework', '{}', 'now')")
    assert db.execute("SELECT COUNT(*) FROM chef_messages").fetchone()[0] == 2
