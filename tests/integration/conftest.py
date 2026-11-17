import os
import threading
from datetime import date

import pytest
from werkzeug.serving import make_server

import ideas
import review
from ideas.config import load_config as ideas_config
from ideas.db import connect
from ideas.migrations import FOLDER as IDEAS_MIGRATIONS
from ideas.migrations import migrate
from review.config import load_config as review_config
from review.migrations import FOLDER as REVIEW_MIGRATIONS

from fakes import PARTIAL, FakeChef, FakeJev

DATABASES = {
    "integration_ideas": (IDEAS_MIGRATIONS, ("evidence", "revisions", "ideas")),
    "integration_review": (REVIEW_MIGRATIONS, ("chef_messages", "gates", "jev_calls", "verdicts")),
}


def server_url():
    url = os.environ.get("TEST_SQL_URL")
    if not url:
        pytest.exit("Set TEST_SQL_URL to a SQL Server login that may create databases, e.g. mssql://sa:<password>@localhost:1433/master")
    return url


def url_for(name):
    return server_url().rsplit("/", 1)[0] + "/" + name


@pytest.fixture(scope="session")
def databases():
    master = connect(server_url(), attempts=10)
    master.raw.autocommit(True)
    for name, (folder, _) in DATABASES.items():
        master.execute(
            "IF DB_ID('{0}') IS NOT NULL BEGIN ALTER DATABASE [{0}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{0}] END".format(name)
        )
        master.execute("CREATE DATABASE [{0}]".format(name))
        connection = connect(url_for(name))
        migrate(connection, folder)
        connection.close()
    master.close()
    return {name: url_for(name) for name in DATABASES}


@pytest.fixture
def count_rows(databases):
    def count(name, table):
        connection = connect(databases[name])
        try:
            return connection.execute("SELECT COUNT(*) AS n FROM " + table).fetchone()["n"]
        finally:
            connection.close()

    return count


@pytest.fixture
def empty_databases(databases):
    for name, (_, tables) in DATABASES.items():
        connection = connect(databases[name])
        for table in tables:
            connection.execute("DELETE FROM " + table)
        used = connection.execute("SELECT OBJECT_NAME(object_id) AS name FROM sys.identity_columns WHERE last_value IS NOT NULL").fetchall()
        for row in used:
            if row["name"] in tables:
                connection.execute("DBCC CHECKIDENT ('" + row["name"] + "', RESEED, 0)")
        connection.commit()
        connection.close()


@pytest.fixture
def system(databases, empty_databases):
    """Starts the review service on a real local port and returns a factory for ideas clients
    that reach it over HTTP, the way the containers do."""
    servers = []

    def start(jev=None, chef=None, search=None, budget=10, review_url=None):
        review_app = review.create_app(
            dict(
                review_config(
                    {
                        "DATABASE_URL": databases["integration_review"],
                        "TYPESAFE_API_KEY": "jev",
                        "COACH_API_KEY": "chef",
                        "JEV_BUDGET_PER_IDEA": str(budget),
                    }
                ),
                JEV_TRANSPORT=jev or FakeJev(PARTIAL),
                CHEF_TRANSPORT=chef or FakeChef(),
                SEARCH_TRANSPORT=search,
            )
        )
        server = make_server("127.0.0.1", 0, review_app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        ideas_app = ideas.create_app(
            dict(
                ideas_config(
                    {
                        "DATABASE_URL": databases["integration_ideas"],
                        "REVIEW_URL": review_url or "http://127.0.0.1:%d" % server.server_port,
                        "REVIEW_TIMEOUT_S": "2",
                        "REVIEW_SLOW_TIMEOUT_S": "10",
                    }
                ),
                TODAY=date(2026, 10, 3),
            )
        )
        return ideas_app.test_client()

    yield start
    for server in servers:
        server.shutdown()
