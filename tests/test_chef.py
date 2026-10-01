import pytest

from pitchkitchen.review.coach import ChefUnavailable, transcript, write_pitch, write_turn
from pitchkitchen.review.logic import focus, heat, next_step, recommend

from fakes import FakeChef

VERDICT = {
    "label": "FIX",
    "rule": "below_cutoff",
    "market_need": 2.5,
    "feasibility": 1.2,
    "differentiation": 2.0,
    "safety_risk": 0.1,
}
CONVERSATION = [
    {"role": "founder", "text": "One-liner: We help X"},
    {"role": "chef", "text": "Who paid?"},
    {"role": "founder", "text": "Nobody yet"},
]


def test_focus_is_the_weakest_score_or_safety_on_a_veto():
    assert focus(VERDICT) == "feasibility"
    assert focus(dict(VERDICT, rule="safety_veto")) == "safety_risk"
    assert recommend("feasibility").startswith("Show you can build it")


def test_kill_and_weak_fixes_turn_up_the_heat():
    weak = dict(VERDICT, market_need=1.4, feasibility=1.4, differentiation=1.0)
    assert heat(dict(VERDICT, label="KILL")) == "harsh"
    assert heat(weak) == "harsh"
    assert heat(dict(weak, market_need=1.5)) == "normal"
    assert heat(VERDICT) == "normal"


def test_two_kills_in_a_row_bin_the_idea():
    assert next_step(["KILL"]) == "open"
    assert next_step(["KILL", "FIX", "KILL"]) == "open"
    assert next_step(["FIX", "KILL", "KILL"]) == "binned"


def test_five_answers_cap_the_interview():
    assert next_step(["FIX"] * 5) == "open"
    assert next_step(["FIX"] * 6) == "capped"
    assert next_step(["FIX"] * 5 + ["KILL", "KILL"]) == "binned"


def test_transcript_names_each_speaker():
    assert transcript(CONVERSATION) == "Founder: One-liner: We help X\n\nChef: Who paid?\n\nFounder: Nobody yet"


def test_write_turn_sends_scores_focus_and_heat():
    chef = FakeChef()
    turn = write_turn(CONVERSATION, VERDICT, "feasibility", "harsh", "open", "key", "model-x", transport=chef)

    body = chef.calls[0]
    system = body["messages"][0]["content"]
    assert body["model"] == "model-x"
    assert "feasibility (can this team" in system
    assert "Tone: brutal" in system
    assert "Founder: Nobody yet" in body["messages"][1]["content"]
    assert turn == {"roast": "Raw.", "question": "Who paid you?"}


def test_a_closing_turn_drops_the_question():
    turn = write_turn(CONVERSATION, VERDICT, "feasibility", "harsh", "binned", "key", transport=FakeChef())
    assert turn["question"] == ""


def test_chef_needs_a_key_and_a_usable_reply():
    with pytest.raises(ChefUnavailable):
        write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "", transport=FakeChef())
    with pytest.raises(ChefUnavailable):
        write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "key", transport=FakeChef({"roast": ""}))
    with pytest.raises(ChefUnavailable):
        write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "key", transport=lambda body, key: {})
    with pytest.raises(ChefUnavailable):
        write_pitch(CONVERSATION, "key", transport=FakeChef({"nope": 1}))


def test_a_busy_model_falls_back_to_the_next_one():
    tried = []

    def busy_first(body, api_key):
        tried.append(body["model"])
        if body["model"] == "busy":
            raise ChefUnavailable()
        return FakeChef()(body, api_key)

    turn = write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "key", "busy, spare", transport=busy_first)

    assert tried == ["busy", "spare"]
    assert turn["question"] == "Who paid you?"
    with pytest.raises(ChefUnavailable):
        write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "key", "busy", transport=busy_first)


def test_write_pitch_returns_the_paragraph():
    assert write_pitch(CONVERSATION, "key", transport=FakeChef()) == "We help students sell textbooks."
