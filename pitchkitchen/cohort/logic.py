"""What a venture lab organizer needs to know about a cohort, from plain dicts.

No tables and no imports from ideas or review: pitchkitchen/organizer.py builds
one dict per idea from both stores and passes the list in.

Each idea dict has: display_name, status, station, answer_count, evidence_count,
gates_passed, labels (verdict label per revision on the branch, pitch first),
and activity (ISO timestamps of everything the founder wrote).
"""

from datetime import date

STUCK_DAYS = 7
ACTIVE_DAYS = 7
RANK = {"UNPROVEN": 0, "PARTIAL": 1, "PROVEN": 2}


def day_of(timestamp):
    return date.fromisoformat(timestamp[:10])


def label_trend(labels):
    scored = [RANK[label] for label in labels if label in RANK]
    if len(scored) < 2:
        return "none"
    if scored[-1] > scored[0]:
        return "up"
    if scored[-1] < scored[0]:
        return "down"
    return "flat"


def latest_label(labels):
    for label in reversed(labels):
        if label in RANK:
            return label
    return "PENDING"


def idea_row(idea, today):
    last = day_of(max(idea["activity"]))
    idle = (today - last).days
    open_idea = idea["status"] not in ("served", "binned")
    return {
        "display_name": idea["display_name"],
        "one_liner": idea.get("one_liner", ""),
        "token": idea.get("token"),
        "status": idea["status"],
        "station": idea["station"],
        "label": latest_label(idea["labels"]),
        "trend": label_trend(idea["labels"]),
        "answers": idea["answer_count"],
        "logs": idea["evidence_count"],
        "gates_passed": idea["gates_passed"],
        "last_activity": last.isoformat(),
        "days_idle": idle,
        "stuck": open_idea and idle >= STUCK_DAYS,
    }


def rows(ideas, today):
    """Stuck ideas first, then the longest idle, so organizers see who needs a nudge."""
    found = [idea_row(idea, today) for idea in ideas]
    return sorted(found, key=lambda row: (not row["stuck"], -row["days_idle"]))


def share(part, whole):
    return round(part / whole, 2) if whole else 0.0


def metrics(ideas, today):
    total = len(ideas)
    active = [i for i in ideas if (today - day_of(max(i["activity"]))).days < ACTIVE_DAYS]
    founders = {}
    for idea in ideas:
        days = founders.setdefault(idea["display_name"].strip().lower(), set())
        days.update(day_of(stamp) for stamp in idea["activity"])
    returning = [name for name, days in founders.items() if len(days) >= 2]
    reached_tasting = [i for i in ideas if i["evidence_count"] > 0 or i["station"] in ("tasting", "takeaway")]
    return {
        "ideas": total,
        "founders": len(founders),
        "active_this_week": len(active),
        "answers_per_idea": round(sum(i["answer_count"] for i in ideas) / total, 1) if total else 0.0,
        "reached_tasting": share(len(reached_tasting), total),
        "returning_founders": share(len(returning), len(founders)),
        "stuck": sum(1 for row in rows(ideas, today) if row["stuck"]),
        "funnel": [
            ("Pitched", total),
            ("Answered Chef", sum(1 for i in ideas if i["answer_count"] > 0)),
            ("Logged a conversation", len(reached_tasting)),
            ("Passed a tasting gate", sum(1 for i in ideas if i["gates_passed"] > 0)),
            ("Served", sum(1 for i in ideas if i["status"] == "served")),
        ],
    }
