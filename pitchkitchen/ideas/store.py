import secrets
from datetime import datetime, timezone

from pitchkitchen.ideas.logic import (
    AFTER_PITCH,
    CLOSED,
    DEFAULT_LEVEL,
    DEFAULT_TONE,
    EVIDENCE_PER_SESSION,
    IdeaClosed,
    IdeaNotFound,
    IdeaTextError,
    clean_answer,
    clean_consent,
    clean_evidence,
    clean_level,
    clean_pitch,
    clean_tone,
    current_head,
    walk_branch,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'cooking'
        CHECK (status IN ('cooking', 'parked', 'served', 'binned')),
    station TEXT NOT NULL DEFAULT 'grill'
        CHECK (station IN ('prep', 'grill', 'tasting', 'plating', 'recipe', 'mise', 'takeaway')),
    token TEXT,
    tone TEXT NOT NULL DEFAULT 'tough' CHECK (tone IN ('supportive', 'tough', 'ramsay')),
    level TEXT NOT NULL DEFAULT 'idea' CHECK (level IN ('new', 'idea', 'tested')),
    pivot_of INTEGER,
    shared INTEGER NOT NULL DEFAULT 0 CHECK (shared IN (0, 1)),
    consent_at TEXT,
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

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL REFERENCES ideas(id),
    session INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'conversation' CHECK (kind IN ('conversation', 'fact')),
    who TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    spoken_on TEXT NOT NULL,
    today_they TEXT NOT NULL DEFAULT '',
    paid TEXT NOT NULL DEFAULT '',
    quote TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""

NEW_COLUMNS = {
    "ideas": {
        "status": "TEXT NOT NULL DEFAULT 'cooking'",
        "station": "TEXT NOT NULL DEFAULT 'grill'",
        "token": "TEXT",
        "tone": "TEXT NOT NULL DEFAULT 'tough'",
        "level": "TEXT NOT NULL DEFAULT 'idea'",
        "pivot_of": "INTEGER",
        "shared": "INTEGER NOT NULL DEFAULT 0",
        "consent_at": "TEXT",
    },
    "evidence": {
        "kind": "TEXT NOT NULL DEFAULT 'conversation'",
        "source": "TEXT NOT NULL DEFAULT ''",
    },
}

COLUMNS = "id, idea_id, parent_id, kind, one_liner, story, answer, created_at"
IDEA_COLUMNS = "id, display_name, status, station, token, tone, level, pivot_of, shared, created_at"


def ensure_schema(connection):
    connection.executescript(SCHEMA)
    for table, wanted in NEW_COLUMNS.items():
        columns = [row["name"] for row in connection.execute("PRAGMA table_info(" + table + ")")]
        for name, definition in wanted.items():
            if name not in columns:
                connection.execute("ALTER TABLE " + table + " ADD COLUMN " + name + " " + definition)
    for row in connection.execute("SELECT id FROM ideas WHERE token IS NULL").fetchall():
        connection.execute("UPDATE ideas SET token = ? WHERE id = ?", (new_token(), row["id"]))
    connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS ideas_token ON ideas(token)")
    connection.commit()


def new_token():
    return secrets.token_urlsafe(16)


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_idea(
    connection,
    display_name,
    one_liner,
    story,
    now=None,
    tone=DEFAULT_TONE,
    shared=False,
    pivot_of=None,
    consent=True,
    level=DEFAULT_LEVEL,
):
    text = clean_pitch(display_name, one_liner, story)
    tone = clean_tone(tone)
    level = clean_level(level)
    clean_consent(consent)
    created_at = now or utc_now()
    cursor = connection.execute(
        """
        INSERT INTO ideas (display_name, station, token, tone, level, pivot_of, shared, consent_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (text["display_name"], AFTER_PITCH, new_token(), tone, level, pivot_of, 1 if shared else 0, created_at, created_at),
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
    return _insert_answer(connection, idea_id, current_head(revisions), answer, now)


def edit_answer(connection, idea_id, revision_id, answer, now=None):
    """Saves a new version of an answer as a sibling: same parent, new id.
    The old answer and anything scored after it stay in the tree, off the branch."""
    revisions = _revisions_for(connection, idea_id)
    target = next((r for r in revisions if r["id"] == revision_id and r["kind"] == "answer"), None)
    if target is None:
        raise IdeaNotFound()
    return _insert_answer(connection, idea_id, target["parent_id"], answer, now)


def _insert_answer(connection, idea_id, parent_id, answer, now):
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
        (idea_id, parent_id, text, now or utc_now()),
    )
    connection.commit()
    return get_idea(connection, idea_id)


def add_evidence(connection, idea_id, session, fields, now=None, today=None):
    status = _status_of(connection, idea_id)
    if status is None:
        raise IdeaNotFound()
    if status in CLOSED:
        raise IdeaClosed(status)
    entry = clean_evidence(fields, today)
    logged = connection.execute(
        "SELECT COUNT(*) AS logged FROM evidence WHERE idea_id = ? AND session = ?",
        (idea_id, session),
    ).fetchone()["logged"]
    if logged >= EVIDENCE_PER_SESSION:
        raise IdeaTextError("who", "This session already has " + str(EVIDENCE_PER_SESSION) + " logs. Ask for the gate.")
    connection.execute(
        """
        INSERT INTO evidence (idea_id, session, kind, who, role, spoken_on, today_they, paid, quote, source, created_at)
        VALUES (:idea_id, :session, :kind, :who, :role, :spoken_on, :today_they, :paid, :quote, :source, :created_at)
        """,
        dict(entry, idea_id=idea_id, session=session, created_at=now or utc_now()),
    )
    connection.commit()
    return evidence_for(connection, idea_id)


def evidence_for(connection, idea_id):
    rows = connection.execute("SELECT * FROM evidence WHERE idea_id = ? ORDER BY id", (idea_id,)).fetchall()
    return [dict(row) for row in rows]


def set_status(connection, idea_id, status):
    current = _status_of(connection, idea_id)
    if current is None:
        raise IdeaNotFound()
    if current in CLOSED:
        raise IdeaClosed(current)
    connection.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))
    connection.commit()


def set_station(connection, idea_id, station):
    connection.execute("UPDATE ideas SET station = ? WHERE id = ?", (station, idea_id))
    connection.commit()


def set_shared(connection, idea_id, shared):
    connection.execute("UPDATE ideas SET shared = ? WHERE id = ?", (1 if shared else 0, idea_id))
    connection.commit()


def delete_idea(connection, idea_id):
    connection.execute("DELETE FROM evidence WHERE idea_id = ?", (idea_id,))
    connection.execute("DELETE FROM revisions WHERE idea_id = ?", (idea_id,))
    connection.execute("UPDATE ideas SET pivot_of = NULL WHERE pivot_of = ?", (idea_id,))
    connection.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    connection.commit()


def get_idea(connection, idea_id):
    idea = connection.execute(
        "SELECT " + IDEA_COLUMNS + " FROM ideas WHERE id = ?",
        (idea_id,),
    ).fetchone()
    if idea is None:
        return None
    revisions = _revisions_for(connection, idea_id)
    found = _idea(idea)
    found["revisions"] = revisions
    found["branch"] = walk_branch(revisions, current_head(revisions))
    return found


def get_idea_by_token(connection, token):
    row = connection.execute("SELECT id FROM ideas WHERE token = ?", (token,)).fetchone()
    return get_idea(connection, row["id"]) if row else None


def get_branch(connection, revision_id):
    row = connection.execute(
        "SELECT idea_id FROM revisions WHERE id = ?",
        (revision_id,),
    ).fetchone()
    if row is None:
        return None
    return walk_branch(_revisions_for(connection, row["idea_id"]), revision_id)


def list_ideas(connection):
    """Every idea with its current branch summary and every timestamp the founder
    wrote something, for boards and the organizer view."""
    ideas = connection.execute("SELECT " + IDEA_COLUMNS + " FROM ideas ORDER BY id DESC").fetchall()
    by_idea = {}
    for row in connection.execute("SELECT " + COLUMNS + " FROM revisions ORDER BY id").fetchall():
        by_idea.setdefault(row["idea_id"], []).append(_revision(row))
    logs = {}
    for row in connection.execute("SELECT idea_id, kind, created_at FROM evidence ORDER BY id").fetchall():
        logs.setdefault(row["idea_id"], []).append(row)

    listed = []
    for idea in ideas:
        revisions = by_idea[idea["id"]]
        branch = walk_branch(revisions, current_head(revisions))
        entries = logs.get(idea["id"], [])
        found = _idea(idea)
        found.update(
            {
                "one_liner": branch[0]["one_liner"],
                "answer_count": len(branch) - 1,
                "head_id": branch[-1]["id"],
                "branch_ids": [revision["id"] for revision in branch],
                "evidence_count": sum(1 for entry in entries if entry["kind"] == "conversation"),
                "fact_count": sum(1 for entry in entries if entry["kind"] == "fact"),
                "activity": sorted([r["created_at"] for r in revisions] + [entry["created_at"] for entry in entries]),
            }
        )
        listed.append(found)
    return listed


def _idea(row):
    return {
        "id": row["id"],
        "display_name": row["display_name"],
        "status": row["status"],
        "station": row["station"],
        "token": row["token"],
        "tone": row["tone"],
        "level": row["level"],
        "pivot_of": row["pivot_of"],
        "shared": bool(row["shared"]),
        "created_at": row["created_at"],
    }


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
