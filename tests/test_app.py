import pytest

from pitchkitchen import create_app

from fakes import FakeChef


def build(tmp_path, **extra):
    config = {"DATA_DIR": tmp_path, "DATABASE": tmp_path / "pitchkitchen.sqlite", "PORT": 5000}
    config.update(extra)
    return create_app(config).test_client()


@pytest.fixture
def client(tmp_path):
    return build(tmp_path)


def pitch(client, story="Story", consent="on", shared=None):
    form = {"display_name": "Ada", "one_liner": "We help X", "story": story, "tone": "tough"}
    if consent:
        form["consent"] = consent
    if shared:
        form["shared"] = shared
    return client.post("/ideas", data=form)


def test_home_creates_sqlite_file(tmp_path, client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Pitch Kitchen" in response.data
    assert b"Google Gemini and Typesafe" in response.data
    assert (tmp_path / "pitchkitchen.sqlite").is_file()


def test_a_pitch_lands_on_a_private_link_as_pending_without_a_key(client):
    response = pitch(client)
    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith("/i/")
    assert "pk_ideas=" in response.headers["Set-Cookie"]

    page = client.get(location)
    assert b"We help X" in page.data
    assert b"PENDING" in page.data


def test_the_idea_page_shows_four_stations_at_the_grill(client):
    location = pitch(client).headers["Location"]
    page = client.get(location).data.decode()

    assert page.count('class="station ') == 4
    assert 'station-current" aria-current="step"' in page
    assert page.index("Grill") < page.index("Tasting") < page.index("Served")


def test_pages_load_htmx_and_boost_every_form_and_link(client):
    page = client.get("/").data.decode()
    assert '<body hx-boost="true">' in page
    assert "/static/htmx.min.js" in page

    script = client.get("/static/htmx.min.js")
    assert script.status_code == 200
    assert b'version:"2.0.11"' in script.data
    script.close()


def test_a_blank_story_or_missing_consent_stays_on_home_with_an_error(client):
    response = pitch(client, story=" ")
    assert response.status_code == 400
    assert b"The story is required." in response.data

    response = pitch(client, consent=None)
    assert response.status_code == 400
    assert b"Tick the box" in response.data


def test_an_answer_joins_the_conversation(client):
    location = pitch(client).headers["Location"]

    response = client.post(location + "/answers", data={"answer": "Ten students paid"})
    assert response.status_code == 302
    assert b"Ten students paid" in client.get(location).data

    assert client.post(location + "/answers", data={"answer": ""}).status_code == 400
    assert client.post(location + "/answers/2/edit", data={"answer": ""}).status_code == 400


def test_unknown_links_are_404(client):
    assert client.get("/i/guess").status_code == 404
    assert client.post("/i/guess/answers", data={"answer": "x"}).status_code == 404
    assert client.post("/i/guess/retry").status_code == 404
    assert client.get("/ideas/1").status_code == 404


def test_home_lists_only_this_browsers_ideas_and_shared_ones(tmp_path):
    first = build(tmp_path)
    second = build(tmp_path)
    private = pitch(first).headers["Location"]
    shared = pitch(first, shared="on").headers["Location"]

    assert first.get("/").data.count(b"We help X") == 2
    other = second.get("/").data.decode()
    assert shared in other
    assert private not in other

    second.post(private + "/share")
    assert private in second.get("/").data.decode()


def test_retry_redirects_to_the_idea(client):
    location = pitch(client).headers["Location"]
    assert client.post(location + "/retry").headers["Location"].endswith(location)


def test_prep_suggests_one_liners(tmp_path):
    client = build(tmp_path, COACH_API_KEY="chef", CHEF_TRANSPORT=FakeChef())
    assert b"Suggest one-liners" in client.get("/").data

    page = client.post("/prep/suggest", data={"story": "Students overpay for books"}).data
    assert page.count(b'data-fill="') == 3
    assert b"Write a rough idea" in client.post("/prep/suggest", data={"story": " "}).data

    busy = build(tmp_path, COACH_API_KEY="chef", CHEF_TRANSPORT=FakeChef({"one_liners": []}))
    assert b"Chef is busy" in busy.post("/prep/suggest", data={"story": "x"}).data


def test_prep_suggestions_are_hidden_without_a_chef_key(client):
    assert b"Suggest one-liners" not in client.get("/").data
