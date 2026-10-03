import sqlite3

import pytest

from pitchkitchen.ideas.logic import (
    IdeaNotFound,
    IdeaTextError,
    clean_answer,
    clean_field,
    clean_pitch,
    STATION_KEYS,
    current_head,
    founder_text,
    rail,
    station_name,
    walk_branch,
)
from pitchkitchen.ideas.store import (
    add_answer,
    create_idea,
    ensure_schema,
    get_branch,
    get_idea,
    list_ideas,
)


def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    ensure_schema(db)
    return db


def node(id, parent_id, kind="answer", answer="a"):
    return {"id": id, "parent_id": parent_id, "kind": kind, "answer": answer}


def test_clean_field_strips_whitespace():
    assert clean_field("display_name", "  Ada  ") == "Ada"


def test_clean_field_rejects_blank_and_long_text():
    with pytest.raises(IdeaTextError) as blank:
        clean_field("story", "   ")
    assert blank.value.field == "story"

    with pytest.raises(IdeaTextError) as too_long:
        clean_field("one_liner", "x" * 201)
    assert too_long.value.field == "one_liner"


def test_clean_pitch_returns_all_three_fields():
    assert clean_pitch(" Ada ", " We help X ", " Story ") == {
        "display_name": "Ada",
        "one_liner": "We help X",
        "story": "Story",
    }


def test_clean_answer_rejects_blank():
    with pytest.raises(IdeaTextError):
        clean_answer(None)


def test_current_head_is_the_newest_revision():
    assert current_head([node(1, None), node(4, 1), node(3, 1)]) == 4
    assert current_head([]) is None


def test_walk_branch_follows_parents_back_to_the_pitch():
    revisions = [node(1, None, "pitch"), node(2, 1), node(3, 2), node(4, 2)]
    assert [r["id"] for r in walk_branch(revisions, 4)] == [1, 2, 4]
    assert [r["id"] for r in walk_branch(revisions, 3)] == [1, 2, 3]


def test_walk_branch_of_unknown_head_is_empty():
    assert walk_branch([node(1, None, "pitch")], 9) == []


def test_founder_text_keeps_only_what_the_founder_wrote():
    branch = [
        {"one_liner": "We help X", "story": "Story", "answer": None},
        {"one_liner": None, "story": None, "answer": "First"},
        {"one_liner": None, "story": None, "answer": "Second"},
    ]
    assert founder_text(branch) == {
        "one_liner": "We help X",
        "story": "Story",
        "answers": ["First", "Second"],
    }


def test_create_idea_stores_the_pitch_as_the_root():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story", now="2026-09-29T10:00:00Z")

    assert idea["display_name"] == "Ada"
    assert len(idea["branch"]) == 1
    pitch = idea["branch"][0]
    assert pitch["kind"] == "pitch"
    assert pitch["parent_id"] is None
    assert pitch["created_at"] == "2026-09-29T10:00:00Z"


def test_create_idea_sets_a_timestamp_when_now_is_omitted():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    assert idea["branch"][0]["created_at"].endswith("Z")


def test_create_idea_rejects_a_blank_story_and_saves_nothing():
    db = connection()
    with pytest.raises(IdeaTextError):
        create_idea(db, "Ada", "We help X", " ")
    assert list_ideas(db) == []


def test_answers_chain_onto_the_previous_revision():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    add_answer(db, idea["id"], "First")
    idea = add_answer(db, idea["id"], "Second")

    branch = idea["branch"]
    assert [r["kind"] for r in branch] == ["pitch", "answer", "answer"]
    assert branch[1]["parent_id"] == branch[0]["id"]
    assert branch[2]["parent_id"] == branch[1]["id"]


def test_add_answer_to_missing_idea_raises():
    db = connection()
    with pytest.raises(IdeaNotFound):
        add_answer(db, 99, "Answer")


def test_schema_rejects_an_answer_without_a_parent():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO revisions (idea_id, kind, answer, created_at) VALUES (?, 'answer', 'x', 'now')",
            (idea["id"],),
        )


def test_get_branch_stops_at_the_requested_revision():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    first = add_answer(db, idea["id"], "First")["branch"][-1]
    add_answer(db, idea["id"], "Second")

    assert [r["answer"] for r in get_branch(db, first["id"])] == [None, "First"]
    assert get_branch(db, 99) is None


def test_list_ideas_shows_the_one_liner_and_answer_count():
    db = connection()
    older = create_idea(db, "Ada", "Older", "Story")
    add_answer(db, older["id"], "First")
    create_idea(db, "Bo", "Newer", "Story")

    listed = list_ideas(db)

    assert [idea["one_liner"] for idea in listed] == ["Newer", "Older"]
    assert listed[1]["answer_count"] == 1
    assert listed[1]["head_id"] == get_idea(db, older["id"])["branch"][-1]["id"]


def test_get_idea_returns_none_when_missing():
    db = connection()
    assert get_idea(db, 4) is None


def test_rail_marks_stations_before_after_and_at_the_current_one():
    stations = rail("grill")

    assert [s["key"] for s in stations] == list(STATION_KEYS)
    assert [s["state"] for s in stations[:3]] == ["done", "current", "upcoming"]
    assert all(s["state"] == "upcoming" for s in stations[2:])


def test_rail_starts_and_ends_at_the_right_stations():
    assert STATION_KEYS[0] == "prep"
    assert STATION_KEYS[-1] == "takeaway"
    assert rail("prep")[0]["state"] == "current"
    assert [s["state"] for s in rail("takeaway")][-2:] == ["done", "current"]


def test_rail_rejects_an_unknown_station():
    with pytest.raises(ValueError):
        rail("dessert")


def test_station_name_is_the_kitchen_name():
    assert station_name("mise") == "Mise en place"


def test_a_new_idea_is_at_the_grill_once_its_pitch_is_saved():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")

    assert idea["station"] == "grill"
    assert list_ideas(db)[0]["station"] == "grill"


def test_schema_rejects_an_unknown_station():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE ideas SET station = 'dessert' WHERE id = ?", (idea["id"],))


def test_an_old_database_gets_status_and_station_columns():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE ideas (id INTEGER PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL)")
    db.execute("INSERT INTO ideas (display_name, created_at) VALUES ('Ada', 'now')")

    ensure_schema(db)

    row = db.execute("SELECT status, station FROM ideas").fetchone()
    assert (row["status"], row["station"]) == ("cooking", "grill")
