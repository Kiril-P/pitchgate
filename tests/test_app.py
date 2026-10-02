import pytest

from pitchkitchen import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(
        {
            "DATA_DIR": tmp_path,
            "DATABASE": tmp_path / "pitchkitchen.sqlite",
            "PORT": 5000,
        }
    )
    return app.test_client()


def pitch(client, story="Story"):
    return client.post(
        "/ideas",
        data={"display_name": "Ada", "one_liner": "We help X", "story": story},
    )


def test_home_creates_sqlite_file(tmp_path, client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Pitch Kitchen" in response.data
    assert (tmp_path / "pitchkitchen.sqlite").is_file()


def test_a_pitch_lands_on_its_page_as_pending_without_a_key(client):
    response = pitch(client)
    assert response.status_code == 302

    page = client.get(response.headers["Location"])
    assert b"We help X" in page.data
    assert b"PENDING" in page.data


def test_the_idea_page_shows_the_station_rail_at_the_grill(client):
    location = pitch(client).headers["Location"]
    page = client.get(location).data.decode()

    assert page.count('class="station ') == 7
    assert 'station-current" aria-current="step"' in page
    assert page.index("Grill") < page.index("Coming next")
    assert "Mise en place" in page
    assert "Grill" in client.get("/").data.decode()


def test_pages_load_htmx_and_boost_every_form_and_link(client):
    page = client.get("/").data.decode()
    assert '<body hx-boost="true">' in page
    assert "/static/htmx.min.js" in page

    script = client.get("/static/htmx.min.js")
    assert script.status_code == 200
    assert b'version:"2.0.11"' in script.data
    script.close()


def test_a_blank_story_stays_on_home_with_an_error(client):
    response = pitch(client, story=" ")
    assert response.status_code == 400
    assert b"The story is required." in response.data


def test_an_answer_joins_the_conversation(client):
    location = pitch(client).headers["Location"]

    response = client.post(location + "/answers", data={"answer": "Ten students paid"})
    assert response.status_code == 302
    assert b"Ten students paid" in client.get(location).data

    blank = client.post(location + "/answers", data={"answer": ""})
    assert blank.status_code == 400


def test_missing_ideas_and_revisions_are_404(client):
    assert client.get("/ideas/9").status_code == 404
    assert client.post("/ideas/9/answers", data={"answer": "x"}).status_code == 404
    assert client.post("/revisions/9/verdict").status_code == 404


def test_retry_scoring_redirects_to_the_idea(client):
    location = pitch(client).headers["Location"]
    response = client.post("/revisions/1/verdict")
    assert response.headers["Location"].endswith(location)
