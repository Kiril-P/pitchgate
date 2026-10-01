from datetime import datetime, timezone

from pitchkitchen.review.jev import JevUnavailable, judge
from pitchkitchen.review.logic import decide, explain, focus, recommend

SCHEMA = """
CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY,
    revision_id INTEGER NOT NULL UNIQUE REFERENCES revisions(id),
    market_need REAL,
    feasibility REAL,
    differentiation REAL,
    safety_risk REAL,
    confidence REAL,
    label TEXT NOT NULL,
    rule TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chef_messages (
    id INTEGER PRIMARY KEY,
    revision_id INTEGER NOT NULL REFERENCES revisions(id),
    kind TEXT NOT NULL CHECK (kind IN ('turn', 'polished')),
    body TEXT NOT NULL,
    question TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (revision_id, kind)
);
"""


def ensure_schema(connection):
    connection.executescript(SCHEMA)
    connection.commit()


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_verdict(connection, revision_id, founder_text, api_key, now=None, transport=None):
    existing = get_verdict(connection, revision_id)
    if existing is not None and existing["label"] != "PENDING":
        return existing

    created_at = now or utc_now()
    if not api_key:
        row = _pending(revision_id, "missing_key", created_at)
    else:
        try:
            measured = judge(founder_text, api_key, transport=transport)
            label, rule = decide(
                measured["market_need"],
                measured["feasibility"],
                measured["differentiation"],
                measured["safety_risk"],
                measured["confidence"],
            )
            row = {
                "revision_id": revision_id,
                "market_need": measured["market_need"],
                "feasibility": measured["feasibility"],
                "differentiation": measured["differentiation"],
                "safety_risk": measured["safety_risk"],
                "confidence": measured["confidence"],
                "label": label,
                "rule": rule,
                "created_at": created_at,
            }
        except JevUnavailable:
            row = _pending(revision_id, "request_failed", created_at)

    _replace(connection, row)
    connection.commit()
    return get_verdict(connection, revision_id)


def get_verdict(connection, revision_id):
    row = connection.execute(
        "SELECT * FROM verdicts WHERE revision_id = ?",
        (revision_id,),
    ).fetchone()
    if row is None:
        return None
    return _verdict(row)


def verdicts_for(connection, revision_ids):
    if not revision_ids:
        return {}
    marks = ",".join("?" for _ in revision_ids)
    rows = connection.execute(
        "SELECT * FROM verdicts WHERE revision_id IN (" + marks + ")",
        tuple(revision_ids),
    ).fetchall()
    return {row["revision_id"]: _verdict(row) for row in rows}


def save_chef(connection, revision_id, kind, body, question="", now=None):
    connection.execute(
        """
        INSERT OR REPLACE INTO chef_messages (revision_id, kind, body, question, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (revision_id, kind, body, question, now or utc_now()),
    )
    connection.commit()


def chef_for(connection, revision_ids):
    """Returns {revision_id: {kind: message}} for the given revisions."""
    if not revision_ids:
        return {}
    marks = ",".join("?" for _ in revision_ids)
    rows = connection.execute(
        "SELECT * FROM chef_messages WHERE revision_id IN (" + marks + ")",
        tuple(revision_ids),
    ).fetchall()
    found = {}
    for row in rows:
        found.setdefault(row["revision_id"], {})[row["kind"]] = {
            "body": row["body"],
            "question": row["question"],
            "created_at": row["created_at"],
        }
    return found


def forget(connection, revision_ids):
    if not revision_ids:
        return
    marks = ",".join("?" for _ in revision_ids)
    connection.execute("DELETE FROM chef_messages WHERE revision_id IN (" + marks + ")", tuple(revision_ids))
    connection.execute("DELETE FROM verdicts WHERE revision_id IN (" + marks + ")", tuple(revision_ids))
    connection.commit()


def _pending(revision_id, rule, created_at):
    return {
        "revision_id": revision_id,
        "market_need": None,
        "feasibility": None,
        "differentiation": None,
        "safety_risk": None,
        "confidence": None,
        "label": "PENDING",
        "rule": rule,
        "created_at": created_at,
    }


def _replace(connection, row):
    connection.execute(
        "DELETE FROM verdicts WHERE revision_id = ?",
        (row["revision_id"],),
    )
    connection.execute(
        """
        INSERT INTO verdicts (
            revision_id, market_need, feasibility, differentiation,
            safety_risk, confidence, label, rule, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["revision_id"],
            row["market_need"],
            row["feasibility"],
            row["differentiation"],
            row["safety_risk"],
            row["confidence"],
            row["label"],
            row["rule"],
            row["created_at"],
        ),
    )


def _verdict(row):
    verdict = {
        "id": row["id"],
        "revision_id": row["revision_id"],
        "market_need": row["market_need"],
        "feasibility": row["feasibility"],
        "differentiation": row["differentiation"],
        "safety_risk": row["safety_risk"],
        "confidence": row["confidence"],
        "label": row["label"],
        "rule": row["rule"],
        "explanation": explain(row["rule"]),
        "created_at": row["created_at"],
        "focus": None,
        "recommendation": None,
    }
    if verdict["label"] != "PENDING":
        verdict["focus"] = focus(verdict)
        verdict["recommendation"] = recommend(verdict["focus"])
    return verdict
