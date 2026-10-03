import sqlite3

import pytest

from pitchkitchen.ideas.logic import founder_text
from pitchkitchen.ideas.store import add_answer, add_evidence, create_idea, ensure_schema as ensure_ideas, evidence_for
from pitchkitchen.review.service import GateNotReady, NotServable, gate_status, run_gate, run_round, serve, sessions_for
from pitchkitchen.review.store import chef_for, ensure_schema as ensure_review, latest_homework

from fakes import GATE_FAIL, PARTIAL, PROVEN, UNPROVEN, FakeChef, FakeJev

SETTINGS = {"jev_key": "jev", "chef_key": "chef", "chef_model": "model-x", "chef_url": "https://chef.test"}


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    ensure_ideas(connection)
    ensure_review(connection)
    return connection


def text_of(db, idea):
    return founder_text(idea["branch"], evidence_for(db, idea["id"]))


def play(db, idea, jev, chef, settings=SETTINGS):
    ids = [revision["id"] for revision in idea["branch"]]
    return run_round(db, ids, text_of(db, idea), settings, jev_transport=jev, chef_transport=chef, idea_id=idea["id"])


def log(db, idea, count, session=1):
    for number in range(count):
        add_evidence(db, idea["id"], session, {"who": "P%d" % number, "spoken_on": "2026-10-01", "quote": "q"})


def test_a_round_scores_then_chef_answers(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    chef = FakeChef()

    result = play(db, idea, FakeJev(PARTIAL), chef)

    assert result == {"verdict": result["verdict"], "step": "open", "paused": None}
    assert result["verdict"]["label"] == "PARTIAL"
    head = idea["branch"][0]["id"]
    assert chef_for(db, [head])[head]["turn"]["question"] == "Who paid you?"
    assert "feasibility" in chef.calls[0]["messages"][0]["content"]


def test_jev_gets_the_question_chef_asked_before_the_answer(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    play(db, idea, FakeJev(PARTIAL), FakeChef())
    idea = add_answer(db, idea["id"], "Ten students paid")
    jev, chef = FakeJev(PARTIAL), FakeChef()

    play(db, idea, jev, chef)

    assert jev.calls[0]["state"]["latest_question"] == "Who paid you?"
    text = chef.calls[0]["messages"][1]["content"]
    assert text.index("Chef: Who paid you? Raw.") < text.index("Founder: Ten students paid")


def test_a_second_unproven_in_a_row_bins_the_idea(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    first = play(db, idea, FakeJev(UNPROVEN), FakeChef())
    idea = add_answer(db, idea["id"], "Still nothing")
    second = play(db, idea, FakeJev(UNPROVEN), FakeChef())

    assert first["step"] == "open"
    assert second["step"] == "binned"


def test_missing_keys_pause_without_losing_anything(db):
    idea = create_idea(db, "Ada", "We help X", "Story")

    assert play(db, idea, FakeJev(PARTIAL), FakeChef(), dict(SETTINGS, jev_key=""))["paused"] == "jev"
    assert play(db, idea, FakeJev(PARTIAL), FakeChef(), dict(SETTINGS, chef_key=""))["paused"] == "chef"
    assert play(db, idea, FakeJev(PARTIAL), FakeChef())["paused"] is None


def test_a_finished_round_is_not_redone(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    jev, chef = FakeJev(PARTIAL), FakeChef()
    play(db, idea, jev, chef)
    play(db, idea, jev, chef)

    assert len(jev.calls) == 1
    assert len(chef.calls) == 1


def test_the_last_answer_of_a_session_gets_homework(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    for number in range(5):
        idea = add_answer(db, idea["id"], "Answer %d" % number)
    result = play(db, idea, FakeJev(PARTIAL), FakeChef())

    ids = [revision["id"] for revision in idea["branch"]]
    assert result["step"] == "homework"
    assert latest_homework(db, ids)["people"][0] == "Sellers"
    assert chef_for(db, ids)[ids[-1]]["turn"]["question"] == ""


def test_the_gate_needs_three_new_logs_and_a_pass_opens_a_session(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    head = idea["branch"][-1]["id"]
    log(db, idea, 2)
    with pytest.raises(GateNotReady):
        run_gate(db, idea["id"], head, text_of(db, idea), SETTINGS, jev_transport=FakeJev())

    log(db, idea, 1)
    sent_back = run_gate(db, idea["id"], head, text_of(db, idea), SETTINGS, jev_transport=FakeJev(tasting=GATE_FAIL))
    assert sent_back["label"] == "SENT_BACK"
    assert not gate_status(db, idea["id"], evidence_for(db, idea["id"]))["ready"]

    log(db, idea, 1)
    jev = FakeJev()
    passed = run_gate(db, idea["id"], head, text_of(db, idea), SETTINGS, jev_transport=jev)
    assert passed["label"] == "PASSED"
    assert len(jev.calls[0]["state"]["conversations"]) == 4
    assert sessions_for(db, idea["id"]) == 2
    assert gate_status(db, idea["id"], evidence_for(db, idea["id"]))["logs"] == []


def test_a_failed_gate_call_can_be_retried_without_new_logs(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    log(db, idea, 3)
    head = idea["branch"][-1]["id"]

    pending = run_gate(db, idea["id"], head, text_of(db, idea), dict(SETTINGS, jev_key=""))
    assert pending["label"] == "PENDING"
    assert gate_status(db, idea["id"], evidence_for(db, idea["id"]))["ready"]


def test_serving_needs_proven_and_three_logs(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    ids = [idea["branch"][0]["id"]]

    with pytest.raises(NotServable):
        serve(db, ids, text_of(db, idea), SETTINGS, chef_transport=FakeChef())

    play(db, idea, FakeJev(PROVEN), FakeChef())
    with pytest.raises(NotServable):
        serve(db, ids, text_of(db, idea), SETTINGS, chef_transport=FakeChef())

    log(db, idea, 3)
    served = serve(db, ids, text_of(db, idea), SETTINGS, chef_transport=FakeChef())
    assert served["pitch"] == "We help students sell textbooks."
    stored = chef_for(db, ids)[ids[0]]
    assert stored["polished"]["body"] == "We help students sell textbooks."
    assert stored["next_steps"]["body"] == ["Run a stall", "Email the union"]
