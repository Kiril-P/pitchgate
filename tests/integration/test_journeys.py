"""Whole founder journeys across both services: the ideas API, the review service over real HTTP, and both databases."""

import socket

from fakes import GATE_FAIL, PARTIAL, PROVEN, UNPROVEN, FakeChef, FakeJev, FakeSearch, grounded

PITCH = {"display_name": "Ada", "one_liner": "We help X", "story": "Story", "consent": True, "tone": "tough"}


def pitch(client, **changes):
    response = client.post("/ideas", json=dict(PITCH, **changes))
    assert response.status_code == 201, response.get_json()
    return "/ideas/" + response.get_json()["idea"]["token"]


def answer(client, location, text):
    return client.post(location + "/answers", json={"answer": text})


def log(client, location, count):
    for number in range(count):
        response = client.post(location + "/evidence", json={"who": "Person %d" % number, "spoken_on": "2026-10-01", "quote": "It took weeks"})
        assert response.status_code == 201, response.get_json()


def page(client, location):
    return client.get(location).get_json()


def test_chef_asks_first_and_the_founder_keeps_answering(system):
    client = system(FakeJev(PARTIAL), FakeChef())
    location = pitch(client)

    found = page(client, location)
    assert found["branch"][0]["chef"]["question"] == "Who paid you?"
    assert found["review"]["answers_left"] == 5

    answer(client, location, "Ten students paid")
    found = page(client, location)
    assert [revision["chef"]["question"] for revision in found["branch"]] == ["Who paid you?", "Who paid you?"]
    assert found["review"]["answers_left"] == 4


def test_five_answers_end_the_session_with_homework(system):
    client = system(FakeJev(PARTIAL), FakeChef())
    location = pitch(client)
    for number in range(5):
        assert answer(client, location, "Answer %d" % number).status_code == 201

    found = page(client, location)
    assert found["review"]["step"] == "homework"
    assert "Bookstore staff" in found["review"]["homework"]["people"]
    assert found["idea"]["station"] == "tasting"
    assert answer(client, location, "One more").status_code == 409


def test_logged_conversations_and_a_passed_gate_open_the_next_session(system):
    jev = FakeJev(PARTIAL)
    client = system(jev, FakeChef(), budget=20)
    location = pitch(client, level="tested")
    for number in range(5):
        answer(client, location, "Answer %d" % number)

    log(client, location, 2)
    assert not page(client, location)["review"]["gate"]["ready"]
    assert client.post(location + "/gate").status_code == 409

    log(client, location, 1)
    jev.tasting = GATE_FAIL
    found = client.post(location + "/gate").get_json()
    assert found["review"]["gate"]["latest"]["label"] == "SENT_BACK"
    assert not found["review"]["gate"]["ready"]

    log(client, location, 1)
    jev.tasting = FakeJev().tasting
    found = client.post(location + "/gate").get_json()
    assert found["review"]["gate"]["latest"]["label"] == "PASSED"
    assert (found["review"]["sessions"], found["review"]["step"], found["idea"]["station"]) == (2, "open", "grill")
    assert answer(client, location, "Three of four pay today").status_code == 201


def test_a_weak_first_session_stays_open_instead_of_binning(system):
    client = system(FakeJev(UNPROVEN), FakeChef())
    location = pitch(client)
    answer(client, location, "Nothing")
    answer(client, location, "Still nothing")

    found = page(client, location)
    assert found["idea"]["status"] == "cooking"
    assert found["review"]["answers_left"] == 3


def test_two_unproven_after_a_passed_gate_bin_the_idea_and_a_pivot_points_back(system):
    client = system(FakeJev(*[PARTIAL] * 6, UNPROVEN), FakeChef())
    location = pitch(client)
    for number in range(5):
        answer(client, location, "Answer %d" % number)
    log(client, location, 3)
    client.post(location + "/gate")
    answer(client, location, "Nothing")
    answer(client, location, "Nothing again")

    found = page(client, location)
    assert (found["idea"]["status"], found["closed"]) == ("binned", True)
    assert answer(client, location, "Please").status_code == 409

    token = location.rsplit("/", 1)[-1]
    pivot = pitch(client, one_liner="We help Y", pivot=token)
    assert page(client, pivot)["pivot_from"] == {"token": token, "one_liner": "We help X"}


def test_proven_needs_three_logs_before_it_is_served_and_the_pack_says_verified(system):
    client = system(FakeJev(PROVEN), FakeChef())
    location = pitch(client)
    assert not page(client, location)["review"]["servable"]
    assert client.post(location + "/serve").status_code == 409

    log(client, location, 3)
    assert page(client, location)["review"]["servable"]
    found = client.post(location + "/serve").get_json()
    assert found["idea"]["status"] == "served"
    assert found["review"]["polished"]["body"] == "We help students sell textbooks."
    assert "Email the union" in found["review"]["next_steps"]["body"]

    client.post(location + "/pack")
    assert "**Verified.**" in client.get(location + "/starter-pack.md").get_data(as_text=True)


def test_editing_an_answer_rescores_the_new_version(system):
    jev = FakeJev(PARTIAL)
    client = system(jev, FakeChef())
    location = pitch(client)
    answer(client, location, "Lots of people")
    answer(client, location, "Second")

    found = client.post(location + "/answers/2", json={"answer": "Twelve people paid"}).get_json()
    assert [revision["answer"] for revision in found["branch"]] == [None, "Twelve people paid"]
    assert found["branch"][-1]["versions"] == 1
    assert len(jev.calls) == 4


def test_save_and_stop_parks_the_idea_until_the_next_answer(system):
    client = system(FakeJev(PARTIAL), FakeChef())
    location = pitch(client)
    token = location.rsplit("/", 1)[-1]

    assert client.post(location + "/park").get_json()["idea"]["status"] == "parked"
    assert client.get("/ideas?mine=" + token).get_json()["boards"][0]["ideas"][0]["status"] == "parked"
    answer(client, location, "Back again")
    assert page(client, location)["idea"]["status"] == "cooking"


def test_chef_failing_shows_paused_and_a_retry_recovers(system):
    chef = FakeChef({"reaction": ""})
    client = system(FakeJev(PARTIAL), chef)
    location = pitch(client)
    assert page(client, location)["review"]["paused"] == "chef"

    chef.reply = {"reaction": "Back.", "question": "Who paid?"}
    found = client.post(location + "/retry").get_json()
    assert found["review"]["paused"] is None
    assert found["branch"][0]["chef"]["question"] == "Who paid?"


def test_deleting_an_idea_empties_both_databases(system, count_rows):
    client = system(FakeJev(PARTIAL), FakeChef())
    location = pitch(client)
    answer(client, location, "Ten students paid")
    log(client, location, 3)
    client.post(location + "/gate")

    assert client.delete(location).status_code == 204
    assert client.get(location).status_code == 404
    left = [count_rows("integration_ideas", t) for t in ("revisions", "evidence")]
    left += [count_rows("integration_review", t) for t in ("verdicts", "chef_messages", "gates", "jev_calls")]
    assert left == [0] * 6


def test_an_idea_stops_calling_jev_once_its_budget_is_spent(system):
    jev = FakeJev(PARTIAL)
    client = system(jev, FakeChef(), budget=2)
    location = pitch(client)
    answer(client, location, "First")
    answer(client, location, "Second")

    assert len(jev.calls) == 2
    found = page(client, location)
    assert found["branch"][-1]["verdict"]["rule"] == "over_budget"
    assert (found["review"]["jev_used"], found["review"]["jev_budget"], found["review"]["paused"]) == (2, 2, "jev")
    assert page(client, pitch(client))["review"]["jev_used"] == 1


def test_chef_failing_on_the_final_pitch_keeps_the_idea_open(system):
    chef = FakeChef()
    client = system(FakeJev(PROVEN), chef)
    location = pitch(client)
    log(client, location, 3)

    chef.reply = {"nope": 1}
    response = client.post(location + "/serve")
    assert response.status_code == 503
    assert "before writing your pitch" in response.get_json()["error"]
    assert page(client, location)["idea"]["status"] == "cooking"


def test_a_beginner_keeps_web_facts_and_opens_the_first_gate_with_them(system):
    client = system(FakeJev(PARTIAL, tasting=GATE_FAIL), FakeChef(), budget=20, search=FakeSearch())
    location = pitch(client, level="new")
    for number in range(5):
        answer(client, location, "Answer %d" % number)

    found = client.post(location + "/facts/search").get_json()["facts"]
    assert found[0]["fact"].startswith("A delivery app charges 3.99 euros")
    kept = [{"quote": fact["fact"], "source": fact["source"], "who": fact["site"]} for fact in found]
    assert client.post(location + "/facts", json={"facts": kept}).status_code == 201
    assert client.post(location + "/facts/search").get_json()["notice"].startswith("Chef found nothing new")
    log(client, location, 1)
    assert (page(client, location)["talks"], page(client, location)["facts"]) == (1, 2)

    gate = client.post(location + "/gate").get_json()["review"]["gate"]["latest"]
    assert (gate["label"], gate["rule"]) == ("PASSED", "gate_starter")


def test_without_web_search_chef_suggests_what_to_look_up(system):
    client = system(FakeJev(PARTIAL), FakeChef(), search=FakeSearch(grounded([])))
    location = pitch(client)
    found = client.post(location + "/facts/search").get_json()
    assert found["searches"][0]["query"] == "menu del dia precio Moncloa"

    stuck = system(FakeJev(PARTIAL), FakeChef({"nope": 1}), search=FakeSearch(grounded([])))
    assert stuck.post(location + "/facts/search").status_code == 503


def test_a_starter_pack_is_written_kept_fresh_and_downloaded(system):
    client = system(FakeJev(PARTIAL), FakeChef())
    location = pitch(client)
    assert client.get(location + "/starter-pack.md").status_code == 404

    found = client.post(location + "/pack").get_json()["review"]
    assert found["pack"]["mvp"][0]["feature"] == "List a book"
    assert found["pack_stale"] is False
    download = client.get(location + "/starter-pack.md")
    assert "attachment" in download.headers["Content-Disposition"]
    assert "**Draft.**" in download.get_data(as_text=True)
    assert "## CLAUDE.md" in download.get_data(as_text=True)

    answer(client, location, "Ten students paid")
    assert page(client, location)["review"]["pack_stale"] is True


def test_chef_failing_on_the_starter_pack_is_a_503(system):
    client = system(FakeJev(PARTIAL), FakeChef())
    location = pitch(client)
    broken = system(FakeJev(PARTIAL), FakeChef({"nope": 1}))
    response = broken.post(location + "/pack")
    assert response.status_code == 503
    assert "before writing your starter pack" in response.get_json()["error"]


def unused_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_with_review_stopped_ideas_keeps_serving_its_own_domain(system):
    client = system(FakeJev(PARTIAL), FakeChef())
    location = pitch(client)
    stopped = system(review_url="http://127.0.0.1:%d" % unused_port())

    found = page(stopped, location)
    assert found["review"] is None
    assert found["branch"][0]["one_liner"] == "We help X"
    assert pitch(stopped, one_liner="Saved anyway")
    refused = answer(stopped, location, "Ten students paid")
    assert refused.status_code == 503
    assert "nothing was saved" in refused.get_json()["error"]
