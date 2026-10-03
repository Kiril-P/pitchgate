from datetime import date

from pitchkitchen import create_app
from pitchkitchen.cohort.logic import idea_row, label_trend, latest_label, metrics, rows

from fakes import PARTIAL, FakeChef, FakeJev

TODAY = date(2026, 10, 20)


def idea(name="Ada", status="cooking", station="grill", answers=2, logs=0, gates=0, labels=None, activity=None):
    return {
        "display_name": name,
        "one_liner": "We help X",
        "token": "t-" + name,
        "status": status,
        "station": station,
        "answer_count": answers,
        "evidence_count": logs,
        "gates_passed": gates,
        "labels": labels or ["PARTIAL"],
        "activity": activity or ["2026-10-19T10:00:00Z"],
    }


def test_trend_compares_first_and_last_scored_labels():
    assert label_trend(["UNPROVEN", "PENDING", "PARTIAL"]) == "up"
    assert label_trend(["PROVEN", "PARTIAL"]) == "down"
    assert label_trend(["PARTIAL", "PARTIAL"]) == "flat"
    assert label_trend(["PENDING"]) == "none"
    assert latest_label(["PARTIAL", "PENDING"]) == "PARTIAL"
    assert latest_label(["PENDING"]) == "PENDING"


def test_an_open_idea_idle_for_a_week_is_stuck():
    row = idea_row(idea(activity=["2026-10-01T10:00:00Z", "2026-10-13T09:00:00Z"]), TODAY)
    assert row["last_activity"] == "2026-10-13"
    assert row["days_idle"] == 7
    assert row["stuck"]
    assert not idea_row(idea(status="served", activity=["2026-10-01T10:00:00Z"]), TODAY)["stuck"]


def test_rows_put_stuck_ideas_first():
    found = rows([idea("Fresh"), idea("Old", activity=["2026-09-01T10:00:00Z"])], TODAY)
    assert [row["display_name"] for row in found] == ["Old", "Fresh"]


def test_metrics_summarise_the_cohort():
    ideas = [
        idea("Ada", answers=5, logs=3, gates=1, activity=["2026-10-10T10:00:00Z", "2026-10-19T10:00:00Z"]),
        idea("ada ", status="served", station="takeaway", answers=3, logs=4, gates=1),
        idea("Bo", answers=0, activity=["2026-09-01T10:00:00Z"]),
    ]

    found = metrics(ideas, TODAY)

    assert found["ideas"] == 3
    assert found["founders"] == 2
    assert found["active_this_week"] == 2
    assert found["answers_per_idea"] == 2.7
    assert found["reached_tasting"] == 0.67
    assert found["returning_founders"] == 0.5
    assert found["stuck"] == 1
    assert found["funnel"] == [
        ("Pitched", 3),
        ("Answered Chef", 2),
        ("Logged a conversation", 2),
        ("Passed a tasting gate", 2),
        ("Served", 1),
    ]


def test_metrics_of_an_empty_cohort():
    assert metrics([], TODAY)["answers_per_idea"] == 0.0
    assert metrics([], TODAY)["returning_founders"] == 0.0


def build(tmp_path, key):
    return create_app(
        {
            "DATA_DIR": tmp_path,
            "DATABASE": tmp_path / "pitchkitchen.sqlite",
            "PORT": 5000,
            "TYPESAFE_API_KEY": "jev",
            "COACH_API_KEY": "chef",
            "JEV_TRANSPORT": FakeJev(PARTIAL),
            "CHEF_TRANSPORT": FakeChef(),
            "ORGANIZER_KEY": key,
        }
    ).test_client()


def test_the_organizer_page_is_off_without_a_key(tmp_path):
    assert build(tmp_path, "").get("/organizer").status_code == 404


def test_the_organizer_page_needs_the_right_key_and_sees_private_ideas(tmp_path):
    client = build(tmp_path, "secret")
    client.post("/ideas", data={"display_name": "Ada", "one_liner": "Private idea", "story": "S", "consent": "on"})

    assert client.get("/organizer").status_code == 403
    wrong = client.get("/organizer?key=nope")
    assert wrong.status_code == 403
    assert b"not right" in wrong.data

    page = client.get("/organizer?key=secret").data.decode()
    assert "Private idea" in page
    assert "Talked to real people" in page
    assert "PARTIAL" in page
