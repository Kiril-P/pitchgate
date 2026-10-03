import pytest

from pitchkitchen.review.coach import (
    ChefUnavailable,
    evidence_text,
    suggest_one_liners,
    transcript,
    write_homework,
    write_pitch,
    write_turn,
)
from pitchkitchen.review.logic import answers_left, focus, heat, next_step, recommend

from fakes import FakeChef

VERDICT = {
    "label": "PARTIAL",
    "rule": "below_cutoff",
    "market_need": 2.5,
    "feasibility": 1.2,
    "differentiation": 2.0,
    "safety_risk": 0.1,
    "market_need_band": "Strong",
    "feasibility_band": "Weak",
    "differentiation_band": "Solid",
}
CONVERSATION = [
    {"role": "founder", "text": "One-liner: We help X"},
    {"role": "chef", "text": "Who paid?"},
    {"role": "founder", "text": "Nobody yet"},
]
LOG = {"who": "Marta", "role": "seller", "spoken_on": "2026-10-01", "today_they": "WhatsApp", "paid": "", "quote": "Took weeks"}


def system_of(chef):
    return chef.calls[0]["messages"][0]["content"]


def test_focus_is_the_weakest_score_or_the_rule_that_fired():
    assert focus(VERDICT) == "feasibility"
    assert focus(dict(VERDICT, rule="safety_veto")) == "safety_risk"
    assert focus(dict(VERDICT, rule="dodged")) == "answered"
    assert focus(dict(VERDICT, rule="mostly_claims")) == "evidence"
    assert recommend("feasibility").startswith("Show you can build it")


def test_unproven_and_weak_partials_turn_up_the_heat():
    weak = dict(VERDICT, market_need=1.4, feasibility=1.4, differentiation=1.0)
    assert heat(dict(VERDICT, label="UNPROVEN")) == "harsh"
    assert heat(weak) == "harsh"
    assert heat(dict(weak, market_need=1.5)) == "normal"
    assert heat(VERDICT) == "normal"


def test_two_unproven_in_a_row_bin_the_idea():
    assert next_step(["UNPROVEN"]) == "open"
    assert next_step(["UNPROVEN", "PARTIAL", "UNPROVEN"]) == "open"
    assert next_step(["PARTIAL", "UNPROVEN", "UNPROVEN"]) == "binned"


def test_five_answers_end_a_session_and_a_passed_gate_opens_five_more():
    assert next_step(["PARTIAL"] * 5) == "open"
    assert next_step(["PARTIAL"] * 6) == "homework"
    assert next_step(["PARTIAL"] * 6, sessions=2) == "open"
    assert next_step(["PARTIAL"] * 11, sessions=2) == "homework"
    assert answers_left(3, 1) == 2
    assert answers_left(7, 1) == 0


def test_transcript_names_each_speaker():
    assert transcript(CONVERSATION) == "Founder: One-liner: We help X\n\nChef: Who paid?\n\nFounder: Nobody yet"


def test_write_turn_sends_bands_focus_tone_and_evidence():
    chef = FakeChef()
    turn = write_turn(
        CONVERSATION, VERDICT, "feasibility", "harsh", "open", "key", "model-x", transport=chef, evidence=[LOG]
    )

    system = system_of(chef)
    assert chef.calls[0]["model"] == "model-x"
    assert "feasibility (can this team" in system
    assert "feasibility Weak" in system
    assert "Never mention Jev" in system
    assert "Marta (seller)" in system
    assert "no swearing" in system
    assert turn == {"reaction": "Raw.", "question": "Who paid you?"}


def test_only_the_ramsay_tone_may_swear():
    chef = FakeChef()
    write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "key", transport=chef, tone="ramsay")
    assert "may swear" in system_of(chef)

    chef = FakeChef()
    write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "key", transport=chef, tone="supportive")
    assert "warm but honest" in system_of(chef)


def test_a_closing_turn_drops_the_question():
    turn = write_turn(CONVERSATION, VERDICT, "feasibility", "harsh", "binned", "key", transport=FakeChef())
    assert turn["question"] == ""
    turn = write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "homework", "key", transport=FakeChef())
    assert turn["question"] == ""


def test_chef_needs_a_key_and_a_usable_reply():
    with pytest.raises(ChefUnavailable):
        write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "", transport=FakeChef())
    with pytest.raises(ChefUnavailable):
        write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "key", transport=FakeChef({"reaction": ""}))
    with pytest.raises(ChefUnavailable):
        write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "key", transport=lambda body, key: {})
    with pytest.raises(ChefUnavailable):
        write_turn(CONVERSATION, VERDICT, "feasibility", "normal", "open", "key", transport=FakeChef(["a list"]))
    with pytest.raises(ChefUnavailable):
        write_pitch(CONVERSATION, "key", transport=FakeChef({"nope": 1}))
    with pytest.raises(ChefUnavailable):
        write_homework(CONVERSATION, "market_need", "key", transport=FakeChef({"people": [], "questions": ["q"]}))
    with pytest.raises(ChefUnavailable):
        suggest_one_liners("idea", "key", transport=FakeChef({"one_liners": "not a list"}))


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


def test_homework_names_people_and_mom_test_questions():
    homework = write_homework(CONVERSATION, "market_need", "key", transport=FakeChef())
    assert homework == {"people": ["Sellers", "Buyers", "Bookstore staff"], "questions": ["When did you last sell a book?"]}


def test_one_liner_suggestions_come_back_as_a_list_of_three():
    chef = FakeChef()
    assert suggest_one_liners("students sell books", "key", transport=chef) == [
        "We help A do B by C",
        "We help D",
        "We help E",
    ]
    assert "students sell books" in chef.calls[0]["messages"][1]["content"]


def test_write_pitch_returns_the_paragraph_and_next_steps():
    served = write_pitch(CONVERSATION, "key", transport=FakeChef(), evidence=[LOG])
    assert served == {"pitch": "We help students sell textbooks.", "next_steps": ["Run a stall", "Email the union"]}


def test_evidence_text_lists_each_conversation():
    assert evidence_text([]).startswith("The founder has not logged")
    assert '"Took weeks"' in evidence_text([LOG])
    assert "paid: n/a" in evidence_text([LOG])
