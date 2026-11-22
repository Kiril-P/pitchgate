from datetime import date

import pytest

from ideas.flows import Flows, SessionOver
from ideas.review_client import ReviewClient, ReviewUnavailable
from ideas.store import get_idea

from fakes import StubReview

PITCH = {"display_name": "Ada", "one_liner": "We help X", "story": "Story", "consent": True}


@pytest.fixture
def review():
    return StubReview()


@pytest.fixture
def flows(db, review):
    return Flows(db, ReviewClient("http://review:8000", 5, 30, transport=review), date(2026, 10, 3))


def test_a_pitch_is_saved_and_moved_to_the_station_reviews_step_names(flows, review, db):
    review.step = "homework"
    idea = get_idea(db, flows.pitch(PITCH))

    assert idea["station"] == "tasting"
    assert [call["path"] for call in review.calls] == ["/rounds"]


def test_review_going_down_keeps_a_pitch_but_refuses_an_answer(flows, review, db):
    review.down = True
    idea = get_idea(db, flows.pitch(PITCH))

    assert flows.page(idea["id"])["review"] is None
    with pytest.raises(ReviewUnavailable):
        flows.answer(idea, "Ten students paid")
    assert len(get_idea(db, idea["id"])["branch"]) == 1


def test_an_answer_after_the_session_ends_is_not_saved(flows, review, db):
    idea = get_idea(db, flows.pitch(PITCH))
    review.step = "homework"

    with pytest.raises(SessionOver):
        flows.answer(idea, "One more")
    assert len(get_idea(db, idea["id"])["branch"]) == 1
