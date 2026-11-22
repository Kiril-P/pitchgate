import pymssql
import pytest

from review.db import connect, parse_url
from review.migrations import FOLDER, batches, migrate

from conftest import recreate


@pytest.fixture
def fresh():
    connection = connect(recreate("review_migrations_test"))
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
    found = parse_url("mssql://review%40app:p%3Ass@db.example:1444/review?encrypt=require")
    assert found == {
        "server": "db.example",
        "port": "1444",
        "user": "review@app",
        "password": "p:ss",
        "database": "review",
        "encryption": "require",
    }
    assert parse_url("mssql://u:p@sql/review")["port"] == "1433"
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
    connect("mssql://u:p@sql/review", attempts=3, sleep=waits.append)

    assert len(attempts) == 3
    assert waits == [2, 4]

    def down(**settings):
        raise pymssql.OperationalError("20002 connection failed")

    monkeypatch.setattr(pymssql, "connect", down)
    with pytest.raises(pymssql.OperationalError):
        connect("mssql://u:p@sql/review", attempts=2, sleep=waits.append)
