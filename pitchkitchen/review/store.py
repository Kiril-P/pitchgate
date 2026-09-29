from datetime import datetime, timezone

from pitchkitchen.review.jev import JevUnavailable, judge
from pitchkitchen.review.logic import decide, explain

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
"""


def ensure_schema(connection):
    connection.executescript(SCHEMA)
    connection.commit()


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_verdict(connection, revision, api_key, now=None, transport=None):
    existing = get_verdict(connection, revision["id"])
    if existing is not None and existing["label"] != "PENDING":
        return existing

    created_at = now or utc_now()
    if not api_key:
        row = _pending(revision["id"], "missing_key", created_at)
    else:
        try:
            measured = judge(
                {
                    "problem": revision["problem"],
                    "audience": revision["audience"],
                    "approach": revision["approach"],
                },
                api_key,
                transport=transport,
            )
            label, rule = decide(
                measured["market_need"],
                measured["feasibility"],
                measured["differentiation"],
                measured["safety_risk"],
                measured["confidence"],
            )
            row = {
                "revision_id": revision["id"],
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
            row = _pending(revision["id"], "request_failed", created_at)

    _replace(connection, row)
    connection.commit()
    return get_verdict(connection, revision["id"])


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
    return {
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
    }
