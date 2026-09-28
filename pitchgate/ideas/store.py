from datetime import datetime, timezone

from pitchgate.ideas.logic import IdeaNotFound, clean_new_idea, clean_revision

SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revisions (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL REFERENCES ideas(id),
    problem TEXT NOT NULL,
    audience TEXT NOT NULL,
    approach TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def ensure_schema(connection):
    connection.executescript(SCHEMA)
    connection.commit()


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_idea(connection, display_name, problem, audience, approach, now=None):
    text = clean_new_idea(display_name, problem, audience, approach)
    created_at = now or utc_now()
    cursor = connection.execute(
        "INSERT INTO ideas (display_name, created_at) VALUES (?, ?)",
        (text["display_name"], created_at),
    )
    idea_id = cursor.lastrowid
    _insert_revision(connection, idea_id, text, created_at)
    connection.commit()
    return get_idea(connection, idea_id)


def revise_idea(connection, idea_id, problem, audience, approach, now=None):
    existing = connection.execute(
        "SELECT id FROM ideas WHERE id = ?",
        (idea_id,),
    ).fetchone()
    if existing is None:
        raise IdeaNotFound()
    text = clean_revision(problem, audience, approach)
    created_at = now or utc_now()
    _insert_revision(connection, idea_id, text, created_at)
    connection.commit()
    return get_idea(connection, idea_id)


def list_ideas(connection):
    rows = connection.execute(
        """
        SELECT
            ideas.id,
            ideas.display_name,
            ideas.created_at,
            revisions.id AS revision_id,
            revisions.problem,
            revisions.audience,
            revisions.approach,
            revisions.created_at AS revision_created_at,
            (
                SELECT COUNT(*)
                FROM revisions AS revision_count
                WHERE revision_count.idea_id = ideas.id
            ) AS revision_count
        FROM ideas
        JOIN revisions ON revisions.id = (
            SELECT id FROM revisions
            WHERE idea_id = ideas.id
            ORDER BY id DESC
            LIMIT 1
        )
        ORDER BY ideas.id DESC
        """
    ).fetchall()
    return [_summary(row) for row in rows]


def get_idea(connection, idea_id):
    idea = connection.execute(
        "SELECT id, display_name, created_at FROM ideas WHERE id = ?",
        (idea_id,),
    ).fetchone()
    if idea is None:
        return None
    revisions = connection.execute(
        """
        SELECT id, problem, audience, approach, created_at
        FROM revisions
        WHERE idea_id = ?
        ORDER BY id DESC
        """,
        (idea_id,),
    ).fetchall()
    return {
        "id": idea["id"],
        "display_name": idea["display_name"],
        "created_at": idea["created_at"],
        "revisions": [_revision(row) for row in revisions],
    }


def _insert_revision(connection, idea_id, text, created_at):
    connection.execute(
        """
        INSERT INTO revisions (idea_id, problem, audience, approach, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (idea_id, text["problem"], text["audience"], text["approach"], created_at),
    )


def _summary(row):
    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "created_at": row["created_at"],
        "revision_count": row["revision_count"],
        "latest": {
            "id": row["revision_id"],
            "problem": row["problem"],
            "audience": row["audience"],
            "approach": row["approach"],
            "created_at": row["revision_created_at"],
        },
    }


def _revision(row):
    return {
        "id": row["id"],
        "problem": row["problem"],
        "audience": row["audience"],
        "approach": row["approach"],
        "created_at": row["created_at"],
    }
