import sqlite3

import pytest

from pitchkitchen.ideas.logic import IdeaTextError, clean_field, clean_new_idea
from pitchkitchen.ideas.store import create_idea, ensure_schema, get_idea, list_ideas, revise_idea
from pitchkitchen.ideas.logic import IdeaNotFound


def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    ensure_schema(db)
    return db


def test_clean_field_strips_whitespace():
    assert clean_field("display_name", "  Ada  ") == "Ada"


def test_clean_field_rejects_blank_and_long_text():
    with pytest.raises(IdeaTextError) as blank:
        clean_field("problem", "   ")
    assert blank.value.field == "problem"

    with pytest.raises(IdeaTextError) as too_long:
        clean_field("audience", "x" * 201)
    assert too_long.value.field == "audience"


def test_clean_new_idea_returns_all_four_fields():
    text = clean_new_idea(" Ada ", " Parking ", " Students ", " An app ")
    assert text == {
        "display_name": "Ada",
        "problem": "Parking",
        "audience": "Students",
        "approach": "An app",
    }


def test_create_idea_sets_a_timestamp_when_now_is_omitted():
    db = connection()
    idea = create_idea(db, "Ada", "Problem", "People", "Approach")
    assert idea["revisions"][0]["created_at"].endswith("Z")


def test_create_idea_stores_one_revision():
    db = connection()
    idea = create_idea(
        db,
        "Ada",
        "Campus parking is guesswork",
        "Students who drive",
        "Show open spots",
        now="2026-09-28T10:00:00Z",
    )

    assert idea["display_name"] == "Ada"
    assert len(idea["revisions"]) == 1
    assert idea["revisions"][0]["problem"] == "Campus parking is guesswork"
    assert idea["revisions"][0]["created_at"] == "2026-09-28T10:00:00Z"


def test_revise_idea_keeps_the_older_revision():
    db = connection()
    created = create_idea(
        db,
        "Ada",
        "First problem",
        "Students",
        "First approach",
        now="2026-09-28T10:00:00Z",
    )
    revised = revise_idea(
        db,
        created["id"],
        "Second problem",
        "Commuters",
        "Second approach",
        now="2026-09-28T11:00:00Z",
    )

    stored = db.execute(
        "SELECT problem FROM revisions WHERE idea_id = ? ORDER BY id",
        (created["id"],),
    ).fetchall()
    assert [row["problem"] for row in stored] == ["First problem", "Second problem"]
    assert revised["revisions"][0]["problem"] == "Second problem"
    assert revised["revisions"][1]["problem"] == "First problem"
    assert revised["display_name"] == "Ada"


def test_list_ideas_uses_the_latest_revision():
    db = connection()
    created = create_idea(db, "Ada", "First", "Students", "Walk", now="2026-09-28T10:00:00Z")
    revise_idea(db, created["id"], "Second", "Students", "Bus", now="2026-09-28T11:00:00Z")

    listed = list_ideas(db)

    assert len(listed) == 1
    assert listed[0]["latest"]["problem"] == "Second"
    assert listed[0]["revision_count"] == 2


def test_revise_missing_idea_raises():
    db = connection()
    with pytest.raises(IdeaNotFound):
        revise_idea(db, 99, "Problem", "People", "Approach")


def test_get_idea_returns_none_when_missing():
    db = connection()
    assert get_idea(db, 4) is None
