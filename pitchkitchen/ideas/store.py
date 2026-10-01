from datetime import datetime, timezone

from pitchkitchen.ideas.logic import (
    CLOSED,
    IdeaClosed,
    IdeaNotFound,
    clean_answer,
    clean_pitch,
    current_head,
    walk_branch,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'cooking'
        CHECK (status IN ('cooking', 'parked', 'served', 'binned')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revisions (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL REFERENCES ideas(id),
    parent_id INTEGER REFERENCES revisions(id),
    kind TEXT NOT NULL CHECK (kind IN ('pitch', 'answer')),
    one_liner TEXT,
    story TEXT,
    answer TEXT,
    created_at TEXT NOT NULL,
    CHECK (
        (kind = 'pitch' AND parent_id IS NULL AND one_liner IS NOT NULL
            AND story IS NOT NULL AND answer IS NULL)
        OR
        (kind = 'answer' AND parent_id IS NOT NULL AND answer IS NOT NULL
            AND one_liner IS NULL AND story IS NULL)
    )
);
"""

COLUMNS = "id, idea_id, parent_id, kind, one_liner, story, answer, created_at"


def ensure_schema(connection):
    connection.executescript(SCHEMA)
    columns = [row["name"] for row in connection.execute("PRAGMA table_info(ideas)")]
    if "status" not in columns:
        connection.execute(
            "ALTER TABLE ideas ADD COLUMN status TEXT NOT NULL DEFAULT 'cooking'"
        )
    connection.commit()


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_idea(connection, display_name, one_liner, story, now=None):
    text = clean_pitch(display_name, one_liner, story)
    created_at = now or utc_now()
    cursor = connection.execute(
        "INSERT INTO ideas (display_name, created_at) VALUES (?, ?)",
        (text["display_name"], created_at),
    )
    idea_id = cursor.lastrowid
    connection.execute(
        """
        INSERT INTO revisions (idea_id, parent_id, kind, one_liner, story, created_at)
        VALUES (?, NULL, 'pitch', ?, ?, ?)
        """,
        (idea_id, text["one_liner"], text["story"], created_at),
    )
    connection.commit()
    return get_idea(connection, idea_id)


def add_answer(connection, idea_id, answer, now=None):
    revisions = _revisions_for(connection, idea_id)
    if not revisions:
        raise IdeaNotFound()
    text = clean_answer(answer)
    status = _status_of(connection, idea_id)
    if status in CLOSED:
        raise IdeaClosed(status)
    connection.execute(
        "UPDATE ideas SET status = 'cooking' WHERE id = ?",
        (idea_id,),
    )
    connection.execute(
        """
        INSERT INTO revisions (idea_id, parent_id, kind, answer, created_at)
        VALUES (?, ?, 'answer', ?, ?)
        """,
        (idea_id, current_head(revisions), text, now or utc_now()),
    )
    connection.commit()
    return get_idea(connection, idea_id)


def set_status(connection, idea_id, status):
    current = _status_of(connection, idea_id)
    if current is None:
        raise IdeaNotFound()
    if current in CLOSED:
        raise IdeaClosed(current)
    connection.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))
    connection.commit()


def delete_idea(connection, idea_id):
    connection.execute("DELETE FROM revisions WHERE idea_id = ?", (idea_id,))
    connection.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    connection.commit()


def get_idea(connection, idea_id):
    idea = connection.execute(
        "SELECT id, display_name, status, created_at FROM ideas WHERE id = ?",
        (idea_id,),
    ).fetchone()
    if idea is None:
        return None
    revisions = _revisions_for(connection, idea_id)
    return {
        "id": idea["id"],
        "display_name": idea["display_name"],
        "status": idea["status"],
        "created_at": idea["created_at"],
        "revisions": revisions,
        "branch": walk_branch(revisions, current_head(revisions)),
    }


def get_branch(connection, revision_id):
    row = connection.execute(
        "SELECT idea_id FROM revisions WHERE id = ?",
        (revision_id,),
    ).fetchone()
    if row is None:
        return None
    return walk_branch(_revisions_for(connection, row["idea_id"]), revision_id)


def list_ideas(connection):
    ideas = connection.execute(
        "SELECT id, display_name, status, created_at FROM ideas ORDER BY id DESC"
    ).fetchall()
    rows = connection.execute(
        "SELECT " + COLUMNS + " FROM revisions ORDER BY id"
    ).fetchall()
    by_idea = {}
    for row in rows:
        by_idea.setdefault(row["idea_id"], []).append(_revision(row))

    listed = []
    for idea in ideas:
        branch = walk_branch(by_idea[idea["id"]], current_head(by_idea[idea["id"]]))
        listed.append(
            {
                "id": idea["id"],
                "display_name": idea["display_name"],
                "status": idea["status"],
                "created_at": idea["created_at"],
                "one_liner": branch[0]["one_liner"],
                "answer_count": len(branch) - 1,
                "head_id": branch[-1]["id"],
            }
        )
    return listed


def _status_of(connection, idea_id):
    row = connection.execute("SELECT status FROM ideas WHERE id = ?", (idea_id,)).fetchone()
    return row["status"] if row else None


def _revisions_for(connection, idea_id):
    rows = connection.execute(
        "SELECT " + COLUMNS + " FROM revisions WHERE idea_id = ? ORDER BY id",
        (idea_id,),
    ).fetchall()
    return [_revision(row) for row in rows]


def _revision(row):
    return {
        "id": row["id"],
        "idea_id": row["idea_id"],
        "parent_id": row["parent_id"],
        "kind": row["kind"],
        "one_liner": row["one_liner"],
        "story": row["story"],
        "answer": row["answer"],
        "created_at": row["created_at"],
    }
