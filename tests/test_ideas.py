import sqlite3
from datetime import date

import pytest

from pitchkitchen.ideas.logic import (
    STATION_KEYS,
    IdeaClosed,
    IdeaNotFound,
    IdeaTextError,
    clean_answer,
    clean_evidence,
    clean_field,
    clean_pitch,
    clean_tone,
    current_head,
    founder_text,
    other_versions,
    rail,
    station_name,
    walk_branch,
)
from pitchkitchen.ideas.store import (
    add_answer,
    add_evidence,
    create_idea,
    delete_idea,
    edit_answer,
    ensure_schema,
    evidence_for,
    get_branch,
    get_idea,
    get_idea_by_token,
    list_ideas,
    set_shared,
    set_status,
)

TODAY = date(2026, 10, 3)


def connection():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    ensure_schema(db)
    return db


def node(id, parent_id, kind="answer", answer="a"):
    return {"id": id, "parent_id": parent_id, "kind": kind, "answer": answer}


def conversation_log(**changes):
    fields = {"who": "Marta", "role": "seller", "spoken_on": "2026-10-01", "today_they": "", "paid": "", "quote": "Weeks"}
    fields.update(changes)
    return fields


def test_clean_field_strips_whitespace():
    assert clean_field("display_name", "  Ada  ") == "Ada"


def test_clean_field_rejects_blank_and_long_text():
    with pytest.raises(IdeaTextError) as blank:
        clean_field("story", "   ")
    assert blank.value.field == "story"

    with pytest.raises(IdeaTextError) as too_long:
        clean_field("one_liner", "x" * 201)
    assert too_long.value.field == "one_liner"
    assert clean_field("role", "", required=False) == ""


def test_clean_pitch_returns_all_three_fields():
    assert clean_pitch(" Ada ", " We help X ", " Story ") == {
        "display_name": "Ada",
        "one_liner": "We help X",
        "story": "Story",
    }


def test_clean_answer_rejects_blank():
    with pytest.raises(IdeaTextError):
        clean_answer(None)


def test_tone_defaults_to_tough_and_rejects_unknown():
    assert clean_tone("") == "tough"
    assert clean_tone("ramsay") == "ramsay"
    with pytest.raises(IdeaTextError):
        clean_tone("rude")


def test_evidence_must_have_happened_already():
    assert clean_evidence(conversation_log(), TODAY)["spoken_on"] == "2026-10-01"
    with pytest.raises(IdeaTextError) as future:
        clean_evidence(conversation_log(spoken_on="2026-10-04"), TODAY)
    assert future.value.field == "spoken_on"
    with pytest.raises(IdeaTextError):
        clean_evidence(conversation_log(spoken_on="soon"), TODAY)
    with pytest.raises(IdeaTextError):
        clean_evidence(conversation_log(quote=" "), TODAY)


def test_current_head_is_the_newest_revision():
    assert current_head([node(1, None), node(4, 1), node(3, 1)]) == 4
    assert current_head([]) is None


def test_walk_branch_follows_parents_back_to_the_pitch():
    revisions = [node(1, None, "pitch"), node(2, 1), node(3, 2), node(4, 2)]
    assert [r["id"] for r in walk_branch(revisions, 4)] == [1, 2, 4]
    assert [r["id"] for r in walk_branch(revisions, 3)] == [1, 2, 3]


def test_walk_branch_of_unknown_head_is_empty():
    assert walk_branch([node(1, None, "pitch")], 9) == []


def test_other_versions_counts_earlier_edits():
    revisions = [node(1, None, "pitch"), node(2, 1), node(3, 1), node(4, 3)]
    branch = walk_branch(revisions, 4)
    assert other_versions(revisions, branch) == {3: 1, 4: 0}


def test_founder_text_keeps_only_what_the_founder_wrote():
    branch = [
        {"one_liner": "We help X", "story": "Story", "answer": None},
        {"one_liner": None, "story": None, "answer": "First"},
    ]
    assert founder_text(branch, [{"who": "Marta"}]) == {
        "one_liner": "We help X",
        "story": "Story",
        "answers": ["First"],
        "evidence": [{"who": "Marta"}],
    }


def test_create_idea_stores_the_pitch_tone_and_a_private_token():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story", now="2026-09-29T10:00:00Z", tone="supportive", shared=True)

    assert idea["display_name"] == "Ada"
    assert idea["tone"] == "supportive"
    assert idea["shared"] is True
    assert len(idea["token"]) >= 20
    assert get_idea_by_token(db, idea["token"])["id"] == idea["id"]
    assert get_idea_by_token(db, "guess") is None
    pitch = idea["branch"][0]
    assert pitch["kind"] == "pitch"
    assert pitch["created_at"] == "2026-09-29T10:00:00Z"


def test_create_idea_needs_consent_and_a_story():
    db = connection()
    with pytest.raises(IdeaTextError) as no_consent:
        create_idea(db, "Ada", "We help X", "Story", consent=False)
    assert no_consent.value.field == "consent"
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
    assert branch[2]["parent_id"] == branch[1]["id"]


def test_editing_an_answer_makes_a_sibling_and_keeps_the_old_one():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    first = add_answer(db, idea["id"], "First")["branch"][-1]
    add_answer(db, idea["id"], "Second")

    idea = edit_answer(db, idea["id"], first["id"], "First, with numbers")

    assert [r["answer"] for r in idea["branch"]] == [None, "First, with numbers"]
    assert idea["branch"][-1]["parent_id"] == first["parent_id"]
    assert len(idea["revisions"]) == 4


def test_editing_needs_an_answer_of_this_idea():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    with pytest.raises(IdeaNotFound):
        edit_answer(db, idea["id"], idea["branch"][0]["id"], "Not an answer")


def test_closed_ideas_take_no_answers_or_logs():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    set_status(db, idea["id"], "binned")
    with pytest.raises(IdeaClosed):
        add_answer(db, idea["id"], "More")
    with pytest.raises(IdeaClosed):
        add_evidence(db, idea["id"], 1, conversation_log(), today=TODAY)
    with pytest.raises(IdeaClosed):
        set_status(db, idea["id"], "parked")


def test_add_answer_to_missing_idea_raises():
    db = connection()
    with pytest.raises(IdeaNotFound):
        add_answer(db, 99, "Answer")
    with pytest.raises(IdeaNotFound):
        add_evidence(db, 99, 1, conversation_log())
    with pytest.raises(IdeaNotFound):
        set_status(db, 99, "parked")


def test_evidence_is_stored_per_session_with_a_cap():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    for _ in range(10):
        add_evidence(db, idea["id"], 1, conversation_log(), today=TODAY)
    with pytest.raises(IdeaTextError):
        add_evidence(db, idea["id"], 1, conversation_log(), today=TODAY)
    add_evidence(db, idea["id"], 2, conversation_log(who="Bo"), today=TODAY)

    logs = evidence_for(db, idea["id"])
    assert len(logs) == 11
    assert logs[-1]["session"] == 2
    assert list_ideas(db)[0]["evidence_count"] == 11


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


def test_list_ideas_shows_the_branch_and_activity():
    db = connection()
    older = create_idea(db, "Ada", "Older", "Story", now="2026-10-01T09:00:00Z")
    add_answer(db, older["id"], "First", now="2026-10-02T09:00:00Z")
    create_idea(db, "Bo", "Newer", "Story")

    listed = list_ideas(db)

    assert [idea["one_liner"] for idea in listed] == ["Newer", "Older"]
    assert listed[1]["answer_count"] == 1
    assert listed[1]["head_id"] == get_idea(db, older["id"])["branch"][-1]["id"]
    assert listed[1]["activity"] == ["2026-10-01T09:00:00Z", "2026-10-02T09:00:00Z"]


def test_sharing_and_deleting_a_pivot_source():
    db = connection()
    source = create_idea(db, "Ada", "Old idea", "Story")
    pivot = create_idea(db, "Ada", "New idea", "Story", pivot_of=source["id"])
    set_shared(db, pivot["id"], True)
    add_evidence(db, source["id"], 1, conversation_log(), today=TODAY)

    delete_idea(db, source["id"])

    assert get_idea(db, source["id"]) is None
    assert get_idea(db, pivot["id"])["pivot_of"] is None
    assert get_idea(db, pivot["id"])["shared"] is True


def test_rail_marks_stations_before_after_and_at_the_current_one():
    stations = rail("grill")
    assert [s["key"] for s in stations] == list(STATION_KEYS)
    assert [s["state"] for s in stations] == ["done", "current", "upcoming", "upcoming"]
    assert rail("takeaway")[-1]["state"] == "current"
    assert station_name("takeaway") == "Served"
    with pytest.raises(ValueError):
        rail("dessert")


def test_a_new_idea_is_at_the_grill_once_its_pitch_is_saved():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    assert idea["station"] == "grill"
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE ideas SET station = 'dessert' WHERE id = ?", (idea["id"],))


def test_an_old_database_gets_the_new_columns_and_tokens():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE ideas (id INTEGER PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL)")
    db.execute("INSERT INTO ideas (display_name, created_at) VALUES ('Ada', 'now')")

    ensure_schema(db)

    row = db.execute("SELECT status, station, tone, level, shared, token FROM ideas").fetchone()
    assert (row["status"], row["station"], row["tone"], row["level"], row["shared"]) == ("cooking", "grill", "tough", "idea", 0)
    assert row["token"]


def test_old_evidence_rows_become_conversations():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE evidence (id INTEGER PRIMARY KEY, idea_id INTEGER NOT NULL, session INTEGER NOT NULL, who TEXT NOT NULL,"
        " role TEXT NOT NULL DEFAULT '', spoken_on TEXT NOT NULL, today_they TEXT NOT NULL DEFAULT '',"
        " paid TEXT NOT NULL DEFAULT '', quote TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    db.execute("INSERT INTO evidence (idea_id, session, who, spoken_on, quote, created_at) VALUES (1, 1, 'Bo', '2026-10-01', 'q', 'now')")

    ensure_schema(db)

    row = db.execute("SELECT kind, source FROM evidence").fetchone()
    assert (row["kind"], row["source"]) == ("conversation", "")


def test_an_idea_starts_at_a_level():
    db = connection()
    assert create_idea(db, "Ada", "We help X", "Story")["level"] == "idea"
    assert create_idea(db, "Ada", "We help X", "Story", level="new")["level"] == "new"
    with pytest.raises(IdeaTextError) as wrong:
        create_idea(db, "Ada", "We help X", "Story", level="expert")
    assert wrong.value.field == "level"


def test_a_fact_needs_a_link_and_keeps_where_it_came_from():
    fact = {"kind": "fact", "quote": "Lunch near campus costs 12 euros.", "source": "https://menu.example/campus", "spoken_on": "2026-10-01"}
    found = clean_evidence(fact, TODAY)
    assert (found["kind"], found["who"], found["source"]) == ("fact", "menu.example", "https://menu.example/campus")
    assert clean_evidence(dict(fact, who="Menu guide"), TODAY)["who"] == "Menu guide"
    for broken in (dict(fact, source=""), dict(fact, source="menu.example"), dict(fact, quote=" ")):
        with pytest.raises(IdeaTextError):
            clean_evidence(broken, TODAY)
    with pytest.raises(IdeaTextError):
        clean_evidence(dict(fact, kind="rumour"), TODAY)
    assert clean_evidence(conversation_log(), TODAY)["kind"] == "conversation"


def test_facts_and_conversations_are_counted_apart():
    db = connection()
    idea = create_idea(db, "Ada", "We help X", "Story")
    add_evidence(db, idea["id"], 1, conversation_log(), today=TODAY)
    add_evidence(db, idea["id"], 1, {"kind": "fact", "quote": "A fact.", "source": "https://a.example", "spoken_on": "2026-10-01"}, today=TODAY)

    listed = list_ideas(db)[0]
    assert (listed["evidence_count"], listed["fact_count"]) == (1, 1)
    assert [entry["kind"] for entry in evidence_for(db, idea["id"])] == ["conversation", "fact"]
