import logging

from ideas import create_app
from ideas.config import load_config

from fakes import StubReview

UNREACHABLE = "mssql://ideas:nope@127.0.0.1:1/ideas"


def build(database_url, review, **environ):
    return create_app(dict(load_config(dict({"DATABASE_URL": database_url}, **environ)), REVIEW_TRANSPORT=review))


def test_health_reflects_only_its_own_database_even_with_review_down(db, database_url):
    review = StubReview()
    review.down = True
    before = db.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()["n"]

    response = build(database_url, review, VERSION="abc1234").test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok", "version": "abc1234"}
    assert review.calls == []
    assert db.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()["n"] == before


def test_health_is_503_when_the_database_cannot_be_reached(db, database_url):
    app = build(database_url, StubReview())
    app.config["DATABASE_URL"] = UNREACHABLE

    response = app.test_client().get("/health")

    assert response.status_code == 503
    assert response.get_json()["db"] == "error"


def test_request_logs_leave_out_the_query_string(db, database_url, caplog):
    client = build(database_url, StubReview(), ORGANIZER_KEY="secret").test_client()
    with caplog.at_level(logging.INFO, logger="ideas.requests"):
        client.get("/organizer?key=secret")
        client.get("/ideas/nope")

    lines = [record.getMessage() for record in caplog.records if record.name == "ideas.requests"]
    assert lines[0].startswith("GET /organizer 200 ")
    assert "secret" not in " ".join(lines)
    assert lines[1].startswith("GET /ideas/nope 404 ")
