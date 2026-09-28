import sqlite3
from pathlib import Path


def connect(db_path):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_database(db_path):
    from pitchgate.ideas.store import ensure_schema

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(path)
    try:
        ensure_schema(connection)
    finally:
        connection.close()
