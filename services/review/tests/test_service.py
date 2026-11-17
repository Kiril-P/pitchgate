import pytest

from review.service import (
    GateNotReady,
    NotServable,
    gate_status,
    run_gate,
    run_round,
    serve,
    sessions_for,
    write_pack,
)
from review.store import chef_for, latest_homework, latest_of

from fakes import GATE_FAIL, PARTIAL, PROVEN, UNPROVEN, FakeChef, FakeIdea, FakeJev

SETTINGS = {"jev_key": "jev", "chef_key": "chef", "chef_model": "model-x", "chef_url": "https://chef.test"}


def play(db, idea, jev, chef, settings=SETTINGS):
    return run_round(db, idea.revision_ids, idea.text(), settings, jev_transport=jev, chef_transport=chef, idea_id=idea.id)


def test_a_round_scores_then_chef_answers(db):
    idea = FakeIdea()
    chef = FakeChef()

    result = play(db, idea, FakeJev(PARTIAL), chef)

    assert result == {"verdict": result["verdict"], "step": "open", "paused": None}
    assert result["verdict"]["label"] == "PARTIAL"
    assert chef_for(db, [idea.head])[idea.head]["turn"]["question"] == "Who paid you?"
    assert "feasibility" in chef.calls[0]["messages"][0]["content"]


def test_jev_gets_the_question_chef_asked_before_the_answer(db):
    idea = FakeIdea()
    play(db, idea, FakeJev(PARTIAL), FakeChef())
    idea.answer("Ten students paid")
    jev, chef = FakeJev(PARTIAL), FakeChef()

    play(db, idea, jev, chef)

    assert jev.calls[0]["state"]["latest_question"] == "Who paid you?"
    text = chef.calls[0]["messages"][1]["content"]
    assert text.index("Chef: Who paid you? Raw.") < text.index("Founder: Ten students paid")


def test_two_unproven_in_the_first_session_keep_the_idea_open(db):
    idea = FakeIdea()
    first = play(db, idea, FakeJev(UNPROVEN), FakeChef())
    idea.answer("Still nothing")
    second = play(db, idea, FakeJev(UNPROVEN), FakeChef())

    assert first["step"] == "open"
    assert second["step"] == "open"


def test_missing_keys_pause_without_losing_anything(db):
    idea = FakeIdea()

    assert play(db, idea, FakeJev(PARTIAL), FakeChef(), dict(SETTINGS, jev_key=""))["paused"] == "jev"
    assert play(db, idea, FakeJev(PARTIAL), FakeChef(), dict(SETTINGS, chef_key=""))["paused"] == "chef"
    assert play(db, idea, FakeJev(PARTIAL), FakeChef())["paused"] is None


def test_a_finished_round_is_not_redone(db):
    idea = FakeIdea()
    jev, chef = FakeJev(PARTIAL), FakeChef()
    play(db, idea, jev, chef)
    play(db, idea, jev, chef)

    assert len(jev.calls) == 1
    assert len(chef.calls) == 1


def test_the_last_answer_of_a_session_gets_homework(db):
    idea = FakeIdea()
    for number in range(5):
        idea.answer("Answer %d" % number)
    result = play(db, idea, FakeJev(PARTIAL), FakeChef())

    assert result["step"] == "homework"
    assert latest_homework(db, idea.revision_ids)["people"][0] == "Sellers"
    assert chef_for(db, idea.revision_ids)[idea.head]["turn"]["question"] == ""


def test_the_gate_needs_three_new_logs_and_a_pass_opens_a_session(db):
    idea = FakeIdea().log(2)
    with pytest.raises(GateNotReady):
        run_gate(db, idea.id, idea.head, idea.text(), SETTINGS, jev_transport=FakeJev())

    idea.log(1)
    sent_back = run_gate(db, idea.id, idea.head, idea.text(), SETTINGS, jev_transport=FakeJev(tasting=GATE_FAIL))
    assert sent_back["label"] == "SENT_BACK"
    assert not gate_status(db, idea.id, idea.evidence)["ready"]

    idea.log(1)
    jev = FakeJev()
    passed = run_gate(db, idea.id, idea.head, idea.text(), SETTINGS, jev_transport=jev)
    assert passed["label"] == "PASSED"
    assert len(jev.calls[0]["state"]["conversations"]) == 4
    assert sessions_for(db, idea.id) == 2
    assert gate_status(db, idea.id, idea.evidence)["logs"] == []


def test_a_failed_gate_call_can_be_retried_without_new_logs(db):
    idea = FakeIdea().log(3)

    pending = run_gate(db, idea.id, idea.head, idea.text(), dict(SETTINGS, jev_key=""))
    assert pending["label"] == "PENDING"
    assert gate_status(db, idea.id, idea.evidence)["ready"]


def test_serving_needs_proven_and_three_logs(db):
    idea = FakeIdea()
    ids = idea.revision_ids

    with pytest.raises(NotServable):
        serve(db, ids, idea.text(), SETTINGS, chef_transport=FakeChef())

    play(db, idea, FakeJev(PROVEN), FakeChef())
    with pytest.raises(NotServable):
        serve(db, ids, idea.text(), SETTINGS, chef_transport=FakeChef())

    idea.log(3)
    served = serve(db, ids, idea.text(), SETTINGS, chef_transport=FakeChef())
    assert served["pitch"] == "We help students sell textbooks."
    stored = chef_for(db, ids)[ids[0]]
    assert stored["polished"]["body"] == "We help students sell textbooks."
    assert stored["next_steps"]["body"] == ["Run a stall", "Email the union"]


def test_facts_alone_cannot_serve_an_idea(db):
    idea = FakeIdea()
    play(db, idea, FakeJev(PROVEN), FakeChef())
    idea.log(3, kind="fact")
    with pytest.raises(NotServable):
        serve(db, idea.revision_ids, idea.text(), SETTINGS, chef_transport=FakeChef())

    idea.log(3)
    assert serve(db, idea.revision_ids, idea.text(), SETTINGS, chef_transport=FakeChef())["pitch"]


def test_a_starter_gate_passes_weak_facts_and_the_bars_still_show(db):
    idea = FakeIdea(level="new").log(3, kind="fact")
    gate = run_gate(db, idea.id, idea.head, idea.text(), SETTINGS, jev_transport=FakeJev(tasting=GATE_FAIL), starter=True)
    assert (gate["label"], gate["rule"]) == ("PASSED", "gate_starter")
    assert gate["evidence_strength"] == 1.0


def test_a_starter_pack_is_stored_with_what_it_was_written_from(db):
    idea = FakeIdea().log(2)
    chef = FakeChef()

    write_pack(db, idea.revision_ids, idea.text(), SETTINGS, verified=False, chef_transport=chef)

    stored = latest_of(db, idea.revision_ids, "starter_pack")
    assert stored["revision_id"] == idea.head
    assert (stored["body"]["verified"], stored["body"]["logs"]) == (False, 2)
    assert stored["body"]["tasks"] == ["Create the Flask app", "Add the books table"]
    assert "P0 (n/a)" in chef.calls[0]["messages"][0]["content"]
