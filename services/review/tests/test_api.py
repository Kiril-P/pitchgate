import pytest

from review import create_app
from review.config import load_config

from fakes import GATE_FAIL, PARTIAL, PROVEN, FakeChef, FakeIdea, FakeJev, FakeSearch, grounded


def build(database_url, jev=None, chef=None, search=None, **extra):
    config = dict(
        load_config({"DATABASE_URL": database_url, "TYPESAFE_API_KEY": "jev", "COACH_API_KEY": "chef"}),
        JEV_TRANSPORT=jev or FakeJev(PARTIAL),
        CHEF_TRANSPORT=chef or FakeChef(),
        SEARCH_TRANSPORT=search,
    )
    config.update(extra)
    return create_app(config).test_client()


@pytest.fixture
def client(db, database_url):
    return build(database_url)


def play(client, idea):
    return client.post(
        "/rounds", json={"idea_id": idea.id, "revision_ids": idea.revision_ids, "founder_text": idea.text(), "level": idea.level}
    )


def state(client, idea):
    return client.post(
        "/ideas/%d/state" % idea.id, json={"revision_ids": idea.revision_ids, "evidence": idea.evidence, "level": idea.level}
    ).get_json()


def test_a_round_returns_the_verdict_and_the_state_shows_chefs_question(client):
    idea = FakeIdea()
    result = play(client, idea).get_json()

    assert (result["verdict"]["label"], result["step"], result["paused"]) == ("PARTIAL", "open", None)
    found = state(client, idea)
    head = str(idea.head)
    assert found["verdicts"][head]["label"] == "PARTIAL"
    assert found["chef"][head]["turn"]["question"] == "Who paid you?"
    assert (found["sessions"], found["answers_left"], found["jev_used"], found["jev_budget"]) == (1, 5, 1, 15)
    assert found["starter_gate"] and not found["servable"]


def test_the_gate_refuses_too_few_logs_then_opens_a_session(client):
    idea = FakeIdea(level="tested").log(2)
    gate = {"idea_id": idea.id, "head_id": idea.head, "founder_text": idea.text(), "level": idea.level}
    refused = client.post("/gates", json=gate)
    assert refused.status_code == 409
    assert "at least 3" in refused.get_json()["error"]

    idea.log(1)
    gate["founder_text"] = idea.text()
    assert client.post("/gates", json=gate).get_json()["label"] == "PASSED"
    assert client.get("/ideas/%d/sessions" % idea.id).get_json() == {"sessions": 2}


def test_serving_needs_proven_and_chef_failing_is_a_503(database_url, db):
    client = build(database_url, jev=FakeJev(PROVEN))
    idea = FakeIdea()
    play(client, idea)
    served = {"revision_ids": idea.revision_ids, "founder_text": idea.text()}
    assert client.post("/serve", json=served).status_code == 409

    idea.log(3)
    served["founder_text"] = idea.text()
    assert state(client, idea)["servable"]
    broken = build(database_url, jev=FakeJev(PROVEN), chef=FakeChef({"nope": 1}))
    assert broken.post("/serve", json=served).status_code == 503
    assert client.post("/serve", json=served).get_json()["pitch"] == "We help students sell textbooks."


def test_a_starter_pack_is_written_and_shows_in_the_state(database_url, db):
    client = build(database_url)
    idea = FakeIdea().log(1)
    pack = {"revision_ids": idea.revision_ids, "founder_text": idea.text(), "verified": False}

    assert build(database_url, chef=FakeChef({"nope": 1})).post("/packs", json=pack).status_code == 503
    assert client.post("/packs", json=pack).get_json()["logs"] == 1
    assert state(client, idea)["pack"]["body"]["tasks"][0] == "Create the Flask app"


def test_forgetting_an_idea_removes_its_verdicts_and_gates(client):
    idea = FakeIdea().log(3)
    play(client, idea)
    client.post("/gates", json={"idea_id": idea.id, "head_id": idea.head, "founder_text": idea.text()})

    response = client.delete("/ideas/%d?revisions=%s" % (idea.id, ",".join(map(str, idea.revision_ids))))

    assert response.status_code == 204
    found = state(client, idea)
    assert (found["verdicts"], found["jev_used"], found["sessions"]) == ({}, 0, 1)
    assert client.delete("/ideas/1?revisions=a,b").status_code == 400


def test_summaries_give_each_ideas_labels_and_passed_gates(client):
    scored, unscored = FakeIdea(), FakeIdea()
    play(client, scored)

    found = client.post(
        "/summaries",
        json={"ideas": [{"id": scored.id, "revision_ids": scored.revision_ids}, {"id": unscored.id, "revision_ids": unscored.revision_ids}]},
    ).get_json()["ideas"]

    assert found[str(scored.id)] == {"labels": ["PARTIAL"], "gates_passed": 0}
    assert found[str(unscored.id)]["labels"] == ["PENDING"]


def test_chef_suggests_one_liners_and_sparks(database_url, db):
    client = build(database_url)
    assert len(client.post("/suggestions/one-liners", json={"text": "Students overpay for books"}).get_json()["suggestions"]) == 3
    assert client.post("/suggestions/one-liners", json={"text": " "}).status_code == 400
    sparks = client.post("/suggestions/sparks", json={"about": "I spend too much on lunch"}).get_json()["suggestions"]
    assert sparks[0]["first_fact"] == "Menu prices near campus"
    assert client.post("/suggestions/sparks", json={"about": ""}).status_code == 400

    busy = build(database_url, chef=FakeChef({"one_liners": [], "sparks": []}))
    assert busy.post("/suggestions/one-liners", json={"text": "x"}).get_json()["error"] == "Chef is busy. Try again in a moment."
    assert busy.post("/suggestions/sparks", json={"about": "x"}).status_code == 503


def test_facts_come_from_search_or_fall_back_to_what_to_look_up(database_url, db):
    pitch = {"one_liner": "We help X", "story": "Story"}
    found = build(database_url, search=FakeSearch()).post("/facts", json=pitch).get_json()
    assert found["facts"][0]["fact"].startswith("A delivery app charges 3.99 euros")

    fallback = build(database_url, search=FakeSearch(grounded([]))).post("/facts", json=pitch).get_json()
    assert fallback["facts"] == []
    assert fallback["searches"][0]["query"] == "menu del dia precio Moncloa"

    stuck = build(database_url, chef=FakeChef({"nope": 1}), search=FakeSearch(grounded([])))
    assert stuck.post("/facts", json=pitch).status_code == 503


def test_bad_requests_get_json_errors(client):
    assert client.post("/rounds", data="nope").get_json() == {"error": "Send a JSON object."}
    assert client.post("/rounds", json={"idea_id": 1}).get_json()["error"] == "Missing: revision_ids, founder_text."
    assert client.post("/ideas/1/state", json={"revision_ids": []}).status_code == 400
    assert client.get("/nowhere").status_code == 404


def test_a_gate_jev_cannot_score_stays_pending(database_url, db):
    client = build(database_url, jev=FakeJev(PARTIAL, tasting=GATE_FAIL))
    idea = FakeIdea(level="tested").log(3)
    gate = client.post("/gates", json={"idea_id": idea.id, "head_id": idea.head, "founder_text": idea.text(), "level": "tested"})
    assert gate.get_json()["label"] == "SENT_BACK"


UI = "http://localhost:8080"


def test_only_the_ui_origin_may_call_from_a_browser(db, database_url):
    client = build(database_url, UI_ORIGIN=UI)

    preflight = client.options("/suggestions/one-liners", headers={"Origin": UI, "Access-Control-Request-Method": "POST"})
    assert preflight.headers["Access-Control-Allow-Origin"] == UI
    assert "Content-Type" in preflight.headers["Access-Control-Allow-Headers"]
    refused = client.post("/suggestions/one-liners", json={"text": " "}, headers={"Origin": UI})
    assert refused.status_code == 400
    assert refused.headers["Access-Control-Allow-Origin"] == UI

    assert "Access-Control-Allow-Origin" not in client.get("/ideas/1/sessions", headers={"Origin": "https://evil.example"}).headers


def test_config_defaults_and_the_environment():
    config = load_config({})
    assert (config["PORT"], config["JEV_BUDGET_PER_IDEA"], config["DATABASE_URL"], config["UI_ORIGIN"]) == (8000, 15, "", "")
    assert load_config({"JEV_BUDGET_PER_IDEA": "3", "PORT": "9000"})["JEV_BUDGET_PER_IDEA"] == 3
    with pytest.raises(RuntimeError):
        create_app(load_config({}))
