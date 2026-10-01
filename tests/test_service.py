import sqlite3

import pytest

from pitchkitchen.ideas.logic import founder_text
from pitchkitchen.ideas.store import add_answer, create_idea, ensure_schema as ensure_ideas
from pitchkitchen.review.service import NotServable, run_round, serve
from pitchkitchen.review.store import chef_for, ensure_schema as ensure_review

from fakes import FIX, KILL, SHIP, FakeChef, FakeJev

SETTINGS = {"jev_key": "jev", "chef_key": "chef", "chef_model": "model-x", "chef_url": "https://chef.test"}


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    ensure_ideas(connection)
    ensure_review(connection)
    return connection


def play(db, branch, jev, chef, settings=SETTINGS):
    ids = [revision["id"] for revision in branch]
    return run_round(db, ids, founder_text(branch), settings, jev_transport=jev, chef_transport=chef)


def test_a_round_scores_then_chef_answers(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    chef = FakeChef()

    result = play(db, idea["branch"], FakeJev(FIX), chef)

    assert result == {"verdict": result["verdict"], "step": "open", "paused": None}
    assert result["verdict"]["label"] == "FIX"
    head = idea["branch"][0]["id"]
    assert chef_for(db, [head])[head]["turn"]["question"] == "Who paid you?"
    assert "feasibility" in chef.calls[0]["messages"][0]["content"]


def test_chef_sees_its_earlier_question_before_the_answer(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    play(db, idea["branch"], FakeJev(FIX), FakeChef())
    idea = add_answer(db, idea["id"], "Ten students paid")
    chef = FakeChef()

    play(db, idea["branch"], FakeJev(FIX), chef)

    text = chef.calls[0]["messages"][1]["content"]
    assert text.index("Chef: Raw. Who paid you?") < text.index("Founder: Ten students paid")


def test_a_second_kill_in_a_row_bins_the_idea(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    first = play(db, idea["branch"], FakeJev(KILL), FakeChef())
    idea = add_answer(db, idea["id"], "Still nothing")
    second = play(db, idea["branch"], FakeJev(KILL), FakeChef())

    assert first["step"] == "open"
    assert second["step"] == "binned"


def test_missing_keys_pause_without_losing_anything(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    no_jev = dict(SETTINGS, jev_key="")
    no_chef = dict(SETTINGS, chef_key="")

    assert play(db, idea["branch"], FakeJev(FIX), FakeChef(), no_jev)["paused"] == "jev"
    assert play(db, idea["branch"], FakeJev(FIX), FakeChef(), no_chef)["paused"] == "chef"
    assert play(db, idea["branch"], FakeJev(FIX), FakeChef())["paused"] is None


def test_a_finished_round_is_not_redone(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    jev, chef = FakeJev(FIX), FakeChef()
    play(db, idea["branch"], jev, chef)
    play(db, idea["branch"], jev, chef)

    assert len(jev.calls) == 1
    assert len(chef.calls) == 1


def test_only_a_ship_can_be_served(db):
    idea = create_idea(db, "Ada", "We help X", "Story")
    ids = [idea["branch"][0]["id"]]
    text = founder_text(idea["branch"])

    with pytest.raises(NotServable):
        serve(db, ids, text, SETTINGS, chef_transport=FakeChef())

    play(db, idea["branch"], FakeJev(SHIP), FakeChef())
    assert serve(db, ids, text, SETTINGS, chef_transport=FakeChef()) == "We help students sell textbooks."
    assert chef_for(db, ids)[ids[0]]["polished"]["body"] == "We help students sell textbooks."
