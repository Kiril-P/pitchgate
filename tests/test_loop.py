import sqlite3
from datetime import date

from pitchkitchen import create_app

from fakes import GATE_FAIL, PARTIAL, PROVEN, UNPROVEN, FakeChef, FakeJev


def make_client(tmp_path, jev, chef, budget=10):
    app = create_app(
        {
            "DATA_DIR": tmp_path,
            "DATABASE": tmp_path / "pitchkitchen.sqlite",
            "PORT": 5000,
            "TYPESAFE_API_KEY": "jev",
            "JEV_BUDGET_PER_IDEA": budget,
            "COACH_API_KEY": "chef",
            "JEV_TRANSPORT": jev,
            "CHEF_TRANSPORT": chef,
            "TODAY": date(2026, 10, 3),
        }
    )
    return app.test_client()


def pitch(client, **changes):
    form = {"display_name": "Ada", "one_liner": "We help X", "story": "Story", "consent": "on", "tone": "tough"}
    form.update(changes)
    return client.post("/ideas", data=form).headers["Location"]


def log(client, location, count):
    for number in range(count):
        response = client.post(
            location + "/evidence", data={"who": "Person %d" % number, "spoken_on": "2026-10-01", "quote": "It took weeks"}
        )
        assert response.status_code == 302


def test_chef_asks_first_and_the_founder_keeps_answering(tmp_path):
    client = make_client(tmp_path, FakeJev(PARTIAL), FakeChef())
    location = pitch(client)

    page = client.get(location).data
    assert page.index(b"Who paid you?") < page.index(b"Raw.")
    assert b"5 left this session" in page

    client.post(location + "/answers", data={"answer": "Ten students paid"})
    page = client.get(location).data
    assert page.count(b"Who paid you?") == 2
    assert b"4 left this session" in page


def test_five_answers_end_the_session_with_homework(tmp_path):
    client = make_client(tmp_path, FakeJev(PARTIAL), FakeChef())
    location = pitch(client)
    for number in range(5):
        assert client.post(location + "/answers", data={"answer": "Answer %d" % number}).status_code == 302

    page = client.get(location).data
    assert b"Session 1 is over" in page
    assert b"Homework from Chef" in page
    assert b"Bookstore staff" in page
    assert b'name="answer" maxlength="1000" rows="3" placeholder' not in page
    assert b'station-current" aria-current="step">\n      <span class="station-number">03' in page
    assert client.post(location + "/answers", data={"answer": "One more"}).status_code == 409


def test_logged_conversations_and_a_passed_gate_open_the_next_session(tmp_path):
    jev = FakeJev(PARTIAL)
    client = make_client(tmp_path, jev, FakeChef(), budget=20)
    location = pitch(client)
    for number in range(5):
        client.post(location + "/answers", data={"answer": "Answer %d" % number})

    log(client, location, 2)
    assert b"1 more this session" in client.get(location).data
    assert client.post(location + "/gate").status_code == 409

    log(client, location, 1)
    jev.tasting = GATE_FAIL
    client.post(location + "/gate")
    page = client.get(location).data
    assert b"Sent back" in page
    assert b"Log a new conversation to try the gate again" in page

    log(client, location, 1)
    jev.tasting = FakeJev().tasting
    client.post(location + "/gate")
    page = client.get(location).data
    assert b"Passed" in page
    assert b"session 2" in page
    assert b"tell Chef what the conversations taught you" in page
    assert client.post(location + "/answers", data={"answer": "Three of four pay today"}).status_code == 302


def test_a_future_conversation_is_refused(tmp_path):
    client = make_client(tmp_path, FakeJev(PARTIAL), FakeChef())
    location = pitch(client)
    response = client.post(location + "/evidence", data={"who": "Bo", "spoken_on": "2026-12-01", "quote": "Maybe"})
    assert response.status_code == 400
    assert b"already happened" in response.data
    assert b'value="Bo"' in response.data


def test_two_unproven_bin_the_idea_and_offer_a_pivot(tmp_path):
    client = make_client(tmp_path, FakeJev(UNPROVEN), FakeChef())
    location = pitch(client)
    client.post(location + "/answers", data={"answer": "Nothing"})

    page = client.get(location).data.decode()
    assert "Binned." in page
    assert "Pivot this idea" in page
    token = location.rsplit("/", 1)[-1]
    assert client.post(location + "/answers", data={"answer": "Please"}).status_code == 409

    form = client.get("/?pivot=" + token).data.decode()
    assert "Pivoting from" in form
    assert 'name="pivot" value="' + token in form

    new = pitch(client, one_liner="We help Y", pivot=token)
    assert "Pivoted from" in client.get(new).data.decode()


def test_proven_needs_three_logs_before_it_can_be_served(tmp_path):
    client = make_client(tmp_path, FakeJev(PROVEN), FakeChef())
    location = pitch(client)
    page = client.get(location).data
    assert b"Log 3 more real conversations to serve it" in page
    assert client.post(location + "/serve").status_code == 409

    log(client, location, 3)
    assert b"Serve it" in client.get(location).data
    client.post(location + "/serve")
    page = client.get(location).data
    assert b"Served." in page
    assert b"We help students sell textbooks." in page
    assert b"Email the union" in page


def test_editing_an_answer_rescores_the_new_version(tmp_path):
    jev = FakeJev(PARTIAL)
    client = make_client(tmp_path, jev, FakeChef())
    location = pitch(client)
    client.post(location + "/answers", data={"answer": "Lots of people"})
    client.post(location + "/answers", data={"answer": "Second"})

    assert client.post(location + "/answers/2/edit", data={"answer": "Twelve people paid"}).status_code == 302
    page = client.get(location).data
    assert b"Twelve people paid" in page
    assert b"Second" not in page
    assert b"edited" in page
    assert len(jev.calls) == 4
    assert client.post(location + "/answers/99/edit", data={"answer": "x"}).status_code == 404


def test_save_and_stop_parks_the_idea_until_the_next_answer(tmp_path):
    client = make_client(tmp_path, FakeJev(PARTIAL), FakeChef())
    location = pitch(client)

    assert client.post(location + "/park").headers["Location"] == "/"
    assert b"parked" in client.get("/").data

    client.post(location + "/answers", data={"answer": "Back again"})
    assert b"Save and stop" in client.get(location).data


def test_chef_failing_shows_a_retry_that_recovers(tmp_path):
    chef = FakeChef({"reaction": ""})
    client = make_client(tmp_path, FakeJev(PARTIAL), chef)
    location = pitch(client)
    page = client.get(location).data
    assert b"Chef stepped out" in page
    assert b'name="answer" maxlength="1000" rows="3" placeholder' not in page

    chef.reply = {"reaction": "Back.", "question": "Who paid?"}
    client.post(location + "/retry")
    page = client.get(location).data
    assert b"Chef stepped out" not in page
    assert b"Who paid?" in page


def test_deleting_an_idea_removes_everything_and_forgets_the_link(tmp_path):
    client = make_client(tmp_path, FakeJev(PARTIAL), FakeChef())
    location = pitch(client)
    client.post(location + "/answers", data={"answer": "Ten students paid"})
    log(client, location, 3)
    client.post(location + "/gate")

    assert client.post(location + "/delete").headers["Location"] == "/"
    assert client.get(location).status_code == 404
    assert b"We help X" not in client.get("/").data

    rows = sqlite3.connect(tmp_path / "pitchkitchen.sqlite").execute(
        "SELECT (SELECT COUNT(*) FROM revisions), (SELECT COUNT(*) FROM verdicts), (SELECT COUNT(*) FROM chef_messages),"
        " (SELECT COUNT(*) FROM evidence), (SELECT COUNT(*) FROM gates), (SELECT COUNT(*) FROM jev_calls)"
    ).fetchone()
    assert rows == (0, 0, 0, 0, 0, 0)


def test_an_idea_stops_calling_jev_once_its_budget_is_spent(tmp_path):
    jev = FakeJev(PARTIAL)
    client = make_client(tmp_path, jev, FakeChef(), budget=2)
    location = pitch(client)
    client.post(location + "/answers", data={"answer": "First"})
    client.post(location + "/answers", data={"answer": "Second"})

    assert len(jev.calls) == 2
    page = client.get(location).data
    assert b"used its whole Jev budget" in page
    assert b"Jev 2 / 2" in page
    assert b"budget-spent" in page

    other = pitch(client)
    assert b"Jev 1 / 2" in client.get(other).data


def test_chef_failing_on_the_final_pitch_keeps_the_idea_open(tmp_path):
    chef = FakeChef()
    client = make_client(tmp_path, FakeJev(PROVEN), chef)
    location = pitch(client)
    log(client, location, 3)

    chef.reply = {"nope": 1}
    response = client.post(location + "/serve")
    assert response.status_code == 503
    assert b"Chef stepped out before writing" in response.data
