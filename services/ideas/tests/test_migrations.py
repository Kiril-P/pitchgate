import pymssql
import pytest

from ideas.db import connect, parse_url
from ideas.migrations import FOLDER, batches, migrate

from conftest import recreate


@pytest.fixture
def fresh():
    connection = connect(recreate("ideas_migrations_test"))
    yield connection
    connection.close()


def test_every_migration_runs_once_and_a_second_boot_applies_nothing(fresh):
    names = sorted(path.name for path in FOLDER.glob("*.sql"))

    assert migrate(fresh) == names
    assert migrate(fresh) == []
    recorded = [row["version"] for row in fresh.execute("SELECT version FROM schema_migrations ORDER BY version")]
    assert recorded == names


def test_a_failing_migration_is_rolled_back_and_not_recorded(fresh, tmp_path):
    (tmp_path / "001_ok.sql").write_text("CREATE TABLE notes (id INT PRIMARY KEY)")
    (tmp_path / "002_broken.sql").write_text("CREATE TABLE half (id INT PRIMARY KEY)\nGO\nSELECT * FROM missing_table")

    with pytest.raises(pymssql.Error):
        migrate(fresh, tmp_path)

    recorded = [row["version"] for row in fresh.execute("SELECT version FROM schema_migrations")]
    assert recorded == ["001_ok.sql"]
    assert fresh.execute("SELECT OBJECT_ID('half') AS found").fetchone()["found"] is None


def test_go_lines_split_batches():
    assert batches("CREATE TABLE a (id INT)\nGO\n\ngo  \nCREATE VIEW b AS SELECT 1 AS x\n") == [
        "CREATE TABLE a (id INT)",
        "CREATE VIEW b AS SELECT 1 AS x",
    ]


def test_database_urls_name_the_server_login_and_database():
    found = parse_url("mssql://ideas%40app:p%3Ass@db.example:1444/ideas?encrypt=require")
    assert found == {
        "server": "db.example",
        "port": "1444",
        "user": "ideas@app",
        "password": "p:ss",
        "database": "ideas",
        "encryption": "require",
    }
    assert parse_url("mssql://u:p@sql/ideas")["port"] == "1433"
    with pytest.raises(ValueError):
        parse_url("sqlite:///data.db")


def test_connect_retries_while_the_database_resumes(monkeypatch):

    attempts, waits = [], []

    def flaky(**settings):
        attempts.append(settings)
        if len(attempts) < 3:
            raise pymssql.OperationalError("40613 database is not currently available")
        return object()

    monkeypatch.setattr(pymssql, "connect", flaky)
    connect("mssql://u:p@sql/ideas", attempts=3, sleep=waits.append)

    assert len(attempts) == 3
    assert waits == [2, 4]

    def down(**settings):
        raise pymssql.OperationalError("20002 connection failed")

    monkeypatch.setattr(pymssql, "connect", down)
    with pytest.raises(pymssql.OperationalError):
        connect("mssql://u:p@sql/ideas", attempts=2, sleep=waits.append)


def test_002_keeps_every_row_and_backfills_when_each_idea_was_last_touched(fresh, tmp_path):
    (tmp_path / "001_init.sql").write_text((FOLDER / "001_init.sql").read_text())
    migrate(fresh, tmp_path)
    fresh.execute(
        "INSERT INTO ideas (display_name, token, created_at) VALUES ('Ada', 't1', '2026-11-01T10:00:00Z'), ('Bo', 't2', '2026-11-02T10:00:00Z')"
    )
    fresh.execute(
        "INSERT INTO revisions (idea_id, parent_id, kind, one_liner, story, created_at) VALUES "
        "(1, NULL, 'pitch', 'We help X', 'S', '2026-11-01T10:00:00Z'), (2, NULL, 'pitch', 'We help Y', 'S', '2026-11-02T10:00:00Z')"
    )
    fresh.execute("INSERT INTO revisions (idea_id, parent_id, kind, answer, created_at) VALUES (1, 1, 'answer', 'Ten paid', '2026-11-05T09:00:00Z')")
    fresh.execute(
        "INSERT INTO evidence (idea_id, session, who, spoken_on, quote, created_at) VALUES (2, 1, 'Lea', '2026-11-06', 'q', '2026-11-07T08:00:00Z')"
    )
    fresh.commit()

    assert migrate(fresh) == ["002_add_updated_at.sql"]

    rows = [tuple(row.values()) for row in fresh.execute("SELECT id, display_name, created_at, updated_at FROM ideas ORDER BY id")]
    assert rows == [
        (1, "Ada", "2026-11-01T10:00:00Z", "2026-11-05T09:00:00Z"),
        (2, "Bo", "2026-11-02T10:00:00Z", "2026-11-07T08:00:00Z"),
    ]
    assert fresh.execute("SELECT COUNT(*) AS n FROM revisions").fetchone()["n"] == 3
    assert fresh.execute("SELECT COUNT(*) AS n FROM evidence").fetchone()["n"] == 1
