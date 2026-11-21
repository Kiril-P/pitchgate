import logging

from review import create_app
from review.config import load_config

UNREACHABLE = "mssql://review:nope@127.0.0.1:1/review"


def build(database_url, **environ):
    return create_app(load_config(dict({"DATABASE_URL": database_url}, **environ)))


def test_health_reads_and_writes_its_own_database_and_keeps_nothing(db, database_url):
    before = db.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()["n"]

    response = build(database_url, VERSION="abc1234").test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok", "version": "abc1234"}
    assert db.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()["n"] == before


def test_health_is_503_when_the_database_cannot_be_reached(db, database_url):
    app = build(database_url)
    app.config["DATABASE_URL"] = UNREACHABLE

    response = app.test_client().get("/health")

    assert response.status_code == 503
    assert response.get_json() == {"status": "error", "db": "error", "version": "dev"}


def test_every_request_logs_method_path_status_and_duration(db, database_url, caplog):
    client = build(database_url).test_client()
    with caplog.at_level(logging.INFO, logger="review.requests"):
        client.get("/health")
        client.post("/rounds", json={})

    lines = [record.getMessage() for record in caplog.records if record.name == "review.requests"]
    assert lines[0].startswith("GET /health 200 ") and lines[0].endswith("ms")
    assert lines[1].startswith("POST /rounds 400 ")
