import os

import pytest

from review.db import connect
from review.migrations import migrate

DATABASE = "review_test"
TABLES = ("chef_messages", "gates", "jev_calls", "verdicts")


def server_url():
    url = os.environ.get("TEST_SQL_URL")
    if not url:
        pytest.exit("Set TEST_SQL_URL to a SQL Server login that may create databases, e.g. mssql://sa:<password>@localhost:1433/master")
    return url


def database_url_for(name):
    return server_url().rsplit("/", 1)[0] + "/" + name


def recreate(name):
    master = connect(server_url(), attempts=10)
    master.raw.autocommit(True)
    master.execute(
        "IF DB_ID('{0}') IS NOT NULL BEGIN ALTER DATABASE [{0}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{0}] END".format(name)
    )
    master.execute("CREATE DATABASE [{0}]".format(name))
    master.close()
    return database_url_for(name)


def empty(connection, tables):
    """Deletes every row and restarts identities at 1, so each test sees the ids a fresh database would hand out."""
    for table in tables:
        connection.execute("DELETE FROM " + table)
    used = connection.execute("SELECT OBJECT_NAME(object_id) AS name FROM sys.identity_columns WHERE last_value IS NOT NULL").fetchall()
    for row in used:
        if row["name"] in tables:
            connection.execute("DBCC CHECKIDENT ('" + row["name"] + "', RESEED, 0)")
    connection.commit()


@pytest.fixture(scope="session")
def database_url():
    url = recreate(DATABASE)
    connection = connect(url)
    migrate(connection)
    connection.close()
    return url


@pytest.fixture
def db(database_url):
    connection = connect(database_url)
    empty(connection, TABLES)
    yield connection
    connection.close()
