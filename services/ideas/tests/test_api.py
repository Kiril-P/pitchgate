from datetime import date

import pytest

from ideas import create_app
from ideas.config import load_config

from fakes import PACK, StubReview

PITCH = {"display_name": "Ada", "one_liner": "We help X", "story": "Story", "consent": True, "tone": "tough"}


def build(database_url, review, **extra):
    config = dict(load_config({"DATABASE_URL": database_url}), REVIEW_TRANSPORT=review, TODAY=date(2026, 10, 3))
    config.update(extra)
    return create_app(config).test_client()


@pytest.fixture
def review():
    return StubReview()


@pytest.fixture
def client(db, database_url, review):
    return build(database_url, review)


def pitch(client, **changes):
    return client.post("/ideas", json=dict(PITCH, **changes))


def token_of(response):
    return response.get_json()["idea"]["token"]


def test_a_pitch_is_saved_then_scored_across_the_seam(client, review):
    response = pitch(client)

    assert response.status_code == 201
    page = response.get_json()
    assert page["idea"]["station"] == "grill"
    assert page["branch"][0]["verdict"]["label"] == "PARTIAL"
    assert page["branch"][0]["chef"]["question"] == "Who paid you?"
    assert page["review"]["answers_left"] == 5
    assert page["notice"] is None
    rounds = [call for call in review.calls if call["path"] == "/rounds"]
    assert rounds[0]["body"]["founder_text"] == {"one_liner": "We help X", "story": "Story", "answers": [], "evidence": []}


def test_every_call_to_review_has_a_timeout_and_slow_calls_get_the_long_one(client, review):
    pitch(client)
    timeouts = {call["path"].split("/")[1]: call["timeout"] for call in review.calls}
    assert timeouts == {"rounds": 30, "ideas": 5}


def test_bad_pitches_name_the_field(client):
    assert pitch(client, story=" ").get_json() == {"error": "The story is required.", "field": "story"}
    assert pitch(client, consent=False).get_json()["field"] == "consent"
    assert pitch(client, level="guru").status_code == 400
    assert client.post("/ideas", data="nope", content_type="application/json").get_json()["field"] == "display_name"
    assert client.post("/ideas", json=["a list"]).get_json() == {"error": "Send a JSON object."}


def test_unknown_links_are_json_404s(client):
    assert client.get("/ideas/guess").get_json() == {"error": "There is no idea at this link."}
    assert client.post("/ideas/guess/answers", json={"answer": "x"}).status_code == 404
    assert client.get("/nowhere").status_code == 404


def test_with_review_down_a_pitch_is_still_saved_and_the_page_still_loads(client, review):
    review.down = True
    response = pitch(client)

    assert response.status_code == 201
    page = response.get_json()
    assert page["review"] is None
    assert "can't be loaded right now" in page["notice"]
    assert page["branch"][0]["one_liner"] == "We help X"
    assert client.get("/ideas/" + token_of(response)).status_code == 200


def test_with_review_down_writes_that_need_it_save_nothing(client, review):
    token = token_of(pitch(client))
    review.down = True

    answered = client.post("/ideas/%s/answers" % token, json={"answer": "Ten students paid"})
    assert answered.status_code == 503
    assert "nothing was saved" in answered.get_json()["error"]
    assert client.post("/ideas/%s/evidence" % token, json={"who": "Bo", "spoken_on": "2026-10-01", "quote": "q"}).status_code == 503
    assert client.delete("/ideas/" + token).status_code == 503

    review.down = False
    page = client.get("/ideas/" + token).get_json()
    assert len(page["branch"]) == 1
    assert page["evidence"] == []


def test_review_answering_garbage_counts_as_down(client, review):
    review.replies[("POST", "/ideas/<id>/state")] = (500, None)
    assert pitch(client).get_json()["review"] is None


def test_a_round_that_runs_past_the_timeout_keeps_the_answer(client, review):
    token = token_of(pitch(client))
    review.slow = {"/rounds"}

    response = client.post("/ideas/%s/answers" % token, json={"answer": "Ten students paid"})

    assert response.status_code == 201
    assert response.get_json()["branch"][-1]["answer"] == "Ten students paid"
    assert response.get_json()["review"] is not None


def test_answers_need_an_open_session_and_edits_stay_on_the_idea(client, review):
    token = token_of(pitch(client))
    first = client.post("/ideas/%s/answers" % token, json={"answer": "Ten students paid"})
    assert first.status_code == 201
    revision_id = first.get_json()["branch"][-1]["id"]
    assert client.post("/ideas/%s/answers" % token, json={"answer": ""}).get_json()["field"] == "answer"

    edited = client.post("/ideas/%s/answers/%d" % (token, revision_id), json={"answer": "Twelve paid"}).get_json()
    assert edited["branch"][-1]["answer"] == "Twelve paid"
    assert edited["branch"][-1]["versions"] == 1
    assert client.post("/ideas/%s/answers/999" % token, json={"answer": "x"}).status_code == 404

    review.step = "homework"
    assert client.post("/ideas/%s/answers" % token, json={"answer": "More"}).status_code == 409


def test_review_steps_move_the_idea_between_stations(client, review):
    review.step = "homework"
    token = token_of(pitch(client))
    assert client.get("/ideas/" + token).get_json()["idea"]["station"] == "tasting"

    review.step = "binned"
    page = client.post("/ideas/%s/retry" % token).get_json()
    assert (page["idea"]["status"], page["closed"]) == ("binned", True)


def test_logs_go_into_the_session_review_names(client, review):
    token = token_of(pitch(client))
    review.sessions = 2
    page = client.post("/ideas/%s/evidence" % token, json={"who": "Bo", "spoken_on": "2026-10-01", "quote": "It took weeks"})

    assert page.status_code == 201
    assert page.get_json()["evidence"][0]["session"] == 2
    assert page.get_json()["talks"] == 1
    future = client.post("/ideas/%s/evidence" % token, json={"who": "Bo", "spoken_on": "2026-12-01", "quote": "Maybe"})
    assert future.get_json()["field"] == "spoken_on"


def test_fact_search_skips_kept_facts_and_kept_facts_are_logged(client, review):
    token = token_of(pitch(client))
    fact = {"fact": "Lunch costs 12 euros.", "source": "https://menu.example", "site": "menu.example"}
    review.facts = {"facts": [fact]}
    assert client.post("/ideas/%s/facts/search" % token).get_json()["facts"] == [fact]

    assert client.post("/ideas/%s/facts" % token, json={"facts": []}).status_code == 400
    kept = client.post("/ideas/%s/facts" % token, json={"facts": [{"quote": fact["fact"], "source": fact["source"], "who": fact["site"]}]})
    assert kept.get_json()["facts"] == 1
    again = client.post("/ideas/%s/facts/search" % token).get_json()
    assert (again["facts"], again["notice"]) == ([], "Chef found nothing new. You already kept these facts.")


def test_review_refusals_reach_the_founder_with_their_status(client, review):
    token = token_of(pitch(client))
    review.replies[("POST", "/gates")] = (409, {"error": "Log at least 3 conversations this session."})
    review.replies[("POST", "/serve")] = (503, {"error": "Chef stepped out before writing your pitch. Try again."})

    assert client.post("/ideas/%s/gate" % token).get_json() == {"error": "Log at least 3 conversations this session."}
    served = client.post("/ideas/%s/serve" % token)
    assert (served.status_code, served.get_json()["error"]) == (503, "Chef stepped out before writing your pitch. Try again.")


def test_a_passed_gate_returns_to_the_grill_and_serving_closes_the_idea(client, review):
    review.step = "homework"
    token = token_of(pitch(client))
    review.step = "open"
    assert client.post("/ideas/%s/gate" % token).get_json()["idea"]["station"] == "grill"

    page = client.post("/ideas/%s/serve" % token).get_json()
    assert (page["idea"]["status"], page["idea"]["station"]) == ("served", "takeaway")
    assert client.post("/ideas/%s/gate" % token).status_code == 409
    assert client.post("/ideas/%s/serve" % token).status_code == 200


def test_the_starter_pack_downloads_once_review_has_one(client, review):
    token = token_of(pitch(client))
    assert client.get("/ideas/%s/starter-pack.md" % token).status_code == 404
    assert client.post("/ideas/%s/pack" % token).status_code == 200

    revision_id = client.get("/ideas/" + token).get_json()["branch"][-1]["id"]
    review.pack = {"revision_id": revision_id, "created_at": "2026-10-03T10:00:00Z", "body": dict(PACK, verified=False, logs=0)}
    page = client.get("/ideas/" + token).get_json()
    assert page["review"]["pack"]["mvp"][0]["feature"] == "List a book"
    assert page["review"]["pack_stale"] is False

    download = client.get("/ideas/%s/starter-pack.md" % token)
    assert download.mimetype == "text/markdown"
    assert "**Draft.**" in download.get_data(as_text=True)


def test_boards_show_this_browsers_ideas_and_shared_ones(client, review):
    mine = token_of(pitch(client))
    shared = token_of(pitch(client, one_liner="Shared idea", shared=True))
    private = token_of(pitch(client, one_liner="Someone else's"))
    client.post("/ideas/%s/park" % mine)

    found = client.get("/ideas?mine=" + mine).get_json()
    assert [idea["token"] for idea in found["boards"][0]["ideas"]] == [mine]
    assert found["boards"][0]["ideas"][0]["status"] == "parked"
    assert found["boards"][0]["ideas"][0]["label"] == "PARTIAL"
    assert [idea["token"] for idea in found["cohort"]] == [shared]
    assert private not in str(found)

    client.post("/ideas/%s/share" % private)
    assert len(client.get("/ideas").get_json()["cohort"]) == 2

    review.down = True
    down = client.get("/ideas?mine=" + mine).get_json()
    assert (down["boards"][0]["ideas"][0]["label"], down["notice"]) == (None, "Scores can't be loaded right now.")


def test_deleting_asks_review_to_forget_first(client, review):
    token = token_of(pitch(client))
    assert client.delete("/ideas/" + token).status_code == 204
    assert review.paths()[-1].startswith("DELETE /ideas/1?revisions=1")
    assert client.get("/ideas/" + token).status_code == 404


def test_a_pivot_points_back_at_its_source(client):
    source = token_of(pitch(client))
    page = pitch(client, one_liner="We help Y", pivot=source).get_json()
    assert page["pivot_from"] == {"token": source, "one_liner": "We help X"}


def test_the_organizer_view_needs_its_key(database_url, db, review):
    assert build(database_url, review).get("/organizer").status_code == 404
    client = build(database_url, review, ORGANIZER_KEY="secret")
    pitch(client, one_liner="Private idea")

    assert client.get("/organizer").get_json()["error"] == "This page needs the organizer key."
    assert client.get("/organizer?key=nope").status_code == 403
    found = client.get("/organizer", headers={"X-Organizer-Key": "secret"}).get_json()
    assert found["rows"][0]["one_liner"] == "Private idea"
    assert found["rows"][0]["label"] == "PARTIAL"
    assert found["metrics"]["ideas"] == 1


UI = "http://localhost:8080"


def test_only_the_ui_origin_may_call_from_a_browser(database_url, db, review):
    client = build(database_url, review, UI_ORIGIN=UI)

    allowed = client.get("/ideas", headers={"Origin": UI})
    assert allowed.headers["Access-Control-Allow-Origin"] == UI
    assert "Origin" in allowed.headers["Vary"]
    preflight = client.options("/ideas/abc", headers={"Origin": UI, "Access-Control-Request-Method": "DELETE"})
    assert "DELETE" in preflight.headers["Access-Control-Allow-Methods"]
    assert "X-Organizer-Key" in preflight.headers["Access-Control-Allow-Headers"]
    assert client.get("/ideas/nope", headers={"Origin": UI}).headers["Access-Control-Allow-Origin"] == UI

    assert "Access-Control-Allow-Origin" not in client.get("/ideas", headers={"Origin": "https://evil.example"}).headers
    assert "Access-Control-Allow-Origin" not in build(database_url, review).get("/ideas", headers={"Origin": UI}).headers


def test_config_defaults():
    config = load_config({})
    assert (config["PORT"], config["REVIEW_URL"], config["REVIEW_TIMEOUT_S"], config["REVIEW_SLOW_TIMEOUT_S"]) == (
        8000,
        "http://review:8000",
        5,
        30,
    )
    assert config["UI_ORIGIN"] == ""
    assert load_config({"UI_ORIGIN": UI + "/"})["UI_ORIGIN"] == UI
    with pytest.raises(RuntimeError):
        create_app(config)


def test_review_url_must_be_http_or_https():
    from ideas.review_client import ReviewClient

    with pytest.raises(ValueError):
        ReviewClient("file:///etc/passwd", 5, 30)
