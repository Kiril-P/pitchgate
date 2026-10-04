import json
from datetime import datetime, timezone

from pitchkitchen.review.jev import JevUnavailable, judge, judge_tasting
from pitchkitchen.review.logic import (
    OLD_LABELS,
    RETRY_CAP,
    band,
    decide,
    decide_tasting,
    explain,
    explain_verdict,
    focus,
    over_budget,
    recommend,
)

CHEF_KINDS = ("turn", "polished", "homework", "next_steps", "starter_pack")
JSON_KINDS = ("homework", "next_steps", "starter_pack")

CHEF_TABLE = """
CREATE TABLE IF NOT EXISTS chef_messages (
    id INTEGER PRIMARY KEY,
    revision_id INTEGER NOT NULL REFERENCES revisions(id),
    kind TEXT NOT NULL CHECK (kind IN ('turn', 'polished', 'homework', 'next_steps', 'starter_pack')),
    body TEXT NOT NULL,
    question TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (revision_id, kind)
);
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY,
    revision_id INTEGER NOT NULL UNIQUE REFERENCES revisions(id),
    market_need REAL,
    feasibility REAL,
    differentiation REAL,
    safety_risk REAL,
    confidence REAL,
    evidence REAL,
    answered REAL,
    label TEXT NOT NULL CHECK (label IN ('UNPROVEN', 'PARTIAL', 'PROVEN', 'PENDING', 'KILL', 'FIX', 'SHIP')),
    rule TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jev_calls (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL,
    revision_id INTEGER NOT NULL REFERENCES revisions(id),
    purpose TEXT NOT NULL CHECK (purpose IN ('verdict', 'gate')),
    ok INTEGER NOT NULL CHECK (ok IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gates (
    id INTEGER PRIMARY KEY,
    idea_id INTEGER NOT NULL,
    session INTEGER NOT NULL,
    last_evidence_id INTEGER NOT NULL,
    evidence_strength REAL,
    pain_frequency REAL,
    willingness_to_pay REAL,
    safety_risk REAL,
    label TEXT NOT NULL CHECK (label IN ('PASSED', 'SENT_BACK', 'PENDING')),
    rule TEXT NOT NULL,
    created_at TEXT NOT NULL
);
""" + CHEF_TABLE


def ensure_schema(connection):
    connection.executescript(SCHEMA)
    columns = [row["name"] for row in connection.execute("PRAGMA table_info(verdicts)")]
    for column in ("evidence", "answered"):
        if column not in columns:
            connection.execute("ALTER TABLE verdicts ADD COLUMN " + column + " REAL")
    for old, new in OLD_LABELS.items():
        connection.execute("UPDATE verdicts SET label = ? WHERE label = ?", (new, old))
    chef_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'chef_messages'"
    ).fetchone()["sql"]
    if "starter_pack" not in chef_sql:
        connection.execute("ALTER TABLE chef_messages RENAME TO chef_messages_old")
        connection.executescript(CHEF_TABLE)
        connection.execute("INSERT INTO chef_messages SELECT * FROM chef_messages_old")
        connection.execute("DROP TABLE chef_messages_old")
    connection.commit()


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_verdict(
    connection, revision_id, founder_text, api_key, now=None, transport=None, idea_id=None, budget=None
):
    """Scores one revision with Jev. With an idea_id, every call is logged, only
    successful calls count toward `budget`, and failures stop after RETRY_CAP."""
    existing = get_verdict(connection, revision_id)
    if existing is not None and existing["label"] != "PENDING":
        return existing

    created_at = now or utc_now()
    if not api_key:
        row = _pending(revision_id, "missing_key", created_at)
    elif idea_id is not None and over_budget(jev_calls_used(connection, idea_id), budget):
        row = _pending(revision_id, "over_budget", created_at)
    elif _failures(connection, revision_id) >= RETRY_CAP:
        row = _pending(revision_id, "retry_cap", created_at)
    else:
        try:
            measured = judge(founder_text, api_key, transport=transport)
        except JevUnavailable:
            measured = None
        if idea_id is not None:
            _log_call(connection, idea_id, revision_id, "verdict", measured is not None, created_at)
        if measured is None:
            row = _pending(revision_id, "request_failed", created_at)
        else:
            label, rule = decide(
                measured["market_need"],
                measured["feasibility"],
                measured["differentiation"],
                measured["safety_risk"],
                measured["confidence"],
                measured["evidence"],
                measured["answered"],
            )
            row = dict(measured, revision_id=revision_id, label=label, rule=rule, created_at=created_at)

    _replace(connection, row)
    connection.commit()
    return get_verdict(connection, revision_id)


def record_gate(
    connection,
    idea_id,
    revision_id,
    session,
    last_evidence_id,
    state,
    api_key,
    budget=None,
    now=None,
    transport=None,
    starter=False,
):
    """Scores this session's tasting logs with one Jev call and stores the gate."""
    created_at = now or utc_now()
    row = {
        "idea_id": idea_id,
        "session": session,
        "last_evidence_id": last_evidence_id,
        "evidence_strength": None,
        "pain_frequency": None,
        "willingness_to_pay": None,
        "safety_risk": None,
        "label": "PENDING",
        "created_at": created_at,
    }
    if not api_key:
        row["rule"] = "missing_key"
    elif over_budget(jev_calls_used(connection, idea_id), budget):
        row["rule"] = "over_budget"
    else:
        try:
            measured = judge_tasting(state, api_key, transport=transport)
        except JevUnavailable:
            measured = None
        _log_call(connection, idea_id, revision_id, "gate", measured is not None, created_at)
        if measured is None:
            row["rule"] = "request_failed"
        else:
            row.update(measured)
            row["label"], row["rule"] = decide_tasting(
                measured["evidence_strength"],
                measured["pain_frequency"],
                measured["willingness_to_pay"],
                measured["safety_risk"],
                starter=starter,
            )
    connection.execute(
        """
        INSERT INTO gates (idea_id, session, last_evidence_id, evidence_strength, pain_frequency,
            willingness_to_pay, safety_risk, label, rule, created_at)
        VALUES (:idea_id, :session, :last_evidence_id, :evidence_strength, :pain_frequency,
            :willingness_to_pay, :safety_risk, :label, :rule, :created_at)
        """,
        row,
    )
    connection.commit()
    return gates_for(connection, idea_id)[-1]


def gates_for(connection, idea_id):
    rows = connection.execute("SELECT * FROM gates WHERE idea_id = ? ORDER BY id", (idea_id,)).fetchall()
    gates = []
    for row in rows:
        gate = dict(row)
        gate["explanation"] = explain(gate["rule"])
        for name in ("evidence_strength", "pain_frequency", "willingness_to_pay"):
            gate[name + "_band"] = band(gate[name])
        gates.append(gate)
    return gates


def gates_passed(connection, idea_id):
    row = connection.execute(
        "SELECT COUNT(*) AS passed FROM gates WHERE idea_id = ? AND label = 'PASSED'",
        (idea_id,),
    ).fetchone()
    return row["passed"]


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


def save_chef_json(connection, revision_id, kind, value, now=None):
    save_chef(connection, revision_id, kind, json.dumps(value), now=now)


def chef_for(connection, revision_ids):
    """Returns {revision_id: {kind: message}} for the given revisions.
    Bodies of the JSON_KINDS are stored as JSON and come back parsed."""
    if not revision_ids:
        return {}
    marks = ",".join("?" for _ in revision_ids)
    rows = connection.execute(
        "SELECT * FROM chef_messages WHERE revision_id IN (" + marks + ")",
        tuple(revision_ids),
    ).fetchall()
    found = {}
    for row in rows:
        body = row["body"]
        if row["kind"] in JSON_KINDS:
            body = json.loads(body)
        found.setdefault(row["revision_id"], {})[row["kind"]] = {
            "body": body,
            "question": row["question"],
            "created_at": row["created_at"],
            "revision_id": row["revision_id"],
        }
    return found


def latest_of(connection, revision_ids, kind):
    """The newest message of one kind on a branch, or None."""
    chef = chef_for(connection, revision_ids)
    for revision_id in reversed(revision_ids):
        if kind in chef.get(revision_id, {}):
            return chef[revision_id][kind]
    return None


def latest_homework(connection, revision_ids):
    found = latest_of(connection, revision_ids, "homework")
    return found["body"] if found else None


def jev_calls_used(connection, idea_id):
    """Successful Jev calls only: a failed call is not charged against the budget."""
    row = connection.execute(
        "SELECT COUNT(*) AS used FROM jev_calls WHERE idea_id = ? AND ok = 1",
        (idea_id,),
    ).fetchone()
    return row["used"]


def _failures(connection, revision_id):
    row = connection.execute(
        "SELECT COUNT(*) AS failed FROM jev_calls WHERE revision_id = ? AND purpose = 'verdict' AND ok = 0",
        (revision_id,),
    ).fetchone()
    return row["failed"]


def _log_call(connection, idea_id, revision_id, purpose, ok, created_at):
    connection.execute(
        """
        INSERT INTO jev_calls (idea_id, revision_id, purpose, ok, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (idea_id, revision_id, purpose, 1 if ok else 0, created_at),
    )


def forget(connection, idea_id, revision_ids):
    connection.execute("DELETE FROM gates WHERE idea_id = ?", (idea_id,))
    connection.execute("DELETE FROM jev_calls WHERE idea_id = ?", (idea_id,))
    if revision_ids:
        marks = ",".join("?" for _ in revision_ids)
        connection.execute("DELETE FROM jev_calls WHERE revision_id IN (" + marks + ")", tuple(revision_ids))
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
        "evidence": None,
        "answered": None,
        "label": "PENDING",
        "rule": rule,
        "created_at": created_at,
    }


def _replace(connection, row):
    connection.execute("DELETE FROM verdicts WHERE revision_id = ?", (row["revision_id"],))
    connection.execute(
        """
        INSERT INTO verdicts (
            revision_id, market_need, feasibility, differentiation,
            safety_risk, confidence, evidence, answered, label, rule, created_at
        ) VALUES (
            :revision_id, :market_need, :feasibility, :differentiation,
            :safety_risk, :confidence, :evidence, :answered, :label, :rule, :created_at
        )
        """,
        row,
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
        "evidence": row["evidence"],
        "answered": row["answered"],
        "label": row["label"],
        "rule": row["rule"],
        "explanation": explain(row["rule"]),
        "created_at": row["created_at"],
        "focus": None,
        "recommendation": None,
    }
    for name in ("market_need", "feasibility", "differentiation", "evidence"):
        verdict[name + "_band"] = band(row[name])
    if verdict["label"] != "PENDING":
        verdict["focus"] = focus(verdict)
        verdict["recommendation"] = recommend(verdict["focus"])
        verdict["explanation"] = explain_verdict(verdict)
    return verdict
