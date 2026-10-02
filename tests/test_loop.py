import sqlite3

from pitchkitchen import create_app

from fakes import FIX, KILL, SHIP, FakeChef, FakeJev


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
        }
    )
    return app.test_client()


def pitch(client):
    response = client.post(
        "/ideas",
        data={"display_name": "Ada", "one_liner": "We help X", "story": "Story"},
    )
    return response.headers["Location"]


def test_chef_replies_and_the_founder_keeps_answering(tmp_path):
    client = make_client(tmp_path, FakeJev(FIX), FakeChef())
    location = pitch(client)

    page = client.get(location).data
    assert b"Who paid you?" in page
    assert b"5 left" in page

    client.post(location + "/answers", data={"answer": "Ten students paid"})
    page = client.get(location).data
    assert page.count(b"Who paid you?") == 2
    assert b"4 left" in page


def test_after_five_answers_the_verdict_stands(tmp_path):
    client = make_client(tmp_path, FakeJev(FIX), FakeChef())
    location = pitch(client)
    for number in range(5):
        assert client.post(location + "/answers", data={"answer": "Answer %d" % number}).status_code == 302

    page = client.get(location).data
    assert b"Five answers in" in page
    assert b'name="answer"' not in page
    assert client.post(location + "/answers", data={"answer": "One more"}).status_code == 409


def test_two_kills_bin_the_idea(tmp_path):
    client = make_client(tmp_path, FakeJev(KILL), FakeChef())
    location = pitch(client)
    client.post(location + "/answers", data={"answer": "Nothing"})

    page = client.get(location).data
    assert b"Binned." in page
    assert b"Start a new idea" in page
    home = client.get("/").data
    assert home.index(b"Binned") < home.index(b"We help X")
    assert client.post(location + "/answers", data={"answer": "Please"}).status_code == 409


def test_ship_can_be_saved_as_final(tmp_path):
    client = make_client(tmp_path, FakeJev(SHIP), FakeChef())
    location = pitch(client)
    assert b"Save as final" in client.get(location).data

    client.post(location + "/serve")
    page = client.get(location).data
    assert b"Served." in page
    assert b"We help students sell textbooks." in page
    assert b"Not scored" in page


def test_serving_a_fix_is_refused(tmp_path):
    client = make_client(tmp_path, FakeJev(FIX), FakeChef())
    location = pitch(client)
    assert client.post(location + "/serve").status_code == 409


def test_save_and_stop_parks_the_idea_until_the_next_answer(tmp_path):
    client = make_client(tmp_path, FakeJev(FIX), FakeChef())
    location = pitch(client)

    assert client.post(location + "/park").headers["Location"] == "/"
    assert b"parked" in client.get("/").data

    client.post(location + "/answers", data={"answer": "Back again"})
    assert b"Save and stop" in client.get(location).data


def test_chef_failing_shows_a_retry_that_recovers(tmp_path):
    chef = FakeChef({"roast": ""})
    client = make_client(tmp_path, FakeJev(FIX), chef)
    location = pitch(client)
    page = client.get(location).data
    assert b"Chef stepped out" in page
    assert b'name="answer"' not in page

    chef.reply = {"roast": "Back.", "question": "Who paid?"}
    client.post("/revisions/1/verdict")
    page = client.get(location).data
    assert b"Chef stepped out" not in page
    assert b"Who paid?" in page


def test_deleting_an_idea_removes_its_whole_conversation(tmp_path):
    client = make_client(tmp_path, FakeJev(FIX), FakeChef())
    location = pitch(client)
    client.post(location + "/answers", data={"answer": "Ten students paid"})

    assert client.post(location + "/delete").headers["Location"] == "/"
    assert client.get(location).status_code == 404
    assert b"We help X" not in client.get("/").data
    assert client.post(location + "/delete").status_code == 404

    rows = sqlite3.connect(tmp_path / "pitchkitchen.sqlite").execute(
        "SELECT (SELECT COUNT(*) FROM revisions), (SELECT COUNT(*) FROM verdicts), (SELECT COUNT(*) FROM chef_messages)"
    ).fetchone()
    assert rows == (0, 0, 0)


def test_an_idea_stops_calling_jev_once_its_budget_is_spent(tmp_path):
    jev = FakeJev(FIX)
    client = make_client(tmp_path, jev, FakeChef(), budget=2)
    location = pitch(client)
    client.post(location + "/answers", data={"answer": "First"})
    client.post(location + "/answers", data={"answer": "Second"})

    assert len(jev.calls) == 2
    page = client.get(location).data
    assert b"used its whole Jev budget" in page

    pitch(client)
    assert len(jev.calls) == 3


def test_chef_failing_on_the_final_pitch_keeps_the_idea_open(tmp_path):
    chef = FakeChef()
    client = make_client(tmp_path, FakeJev(SHIP), chef)
    location = pitch(client)

    chef.reply = {"nope": 1}
    response = client.post(location + "/serve")
    assert response.status_code == 503
    assert b"Chef stepped out before writing" in response.data
