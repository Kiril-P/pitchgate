"""Everything the ideas service does together with review: one method per founder or organizer action.

Each method decides what crosses the seam and what happens when review can't be reached, and returns
plain data. The routes in api.py only read the request, call one of these, and turn the result into JSON.
"""

from ideas.cohort import metrics, rows
from ideas.logic import CLOSED, IdeaClosed, founder_text, station_name
from ideas.pack import render_pack
from ideas.review_client import ReviewUnavailable
from ideas.store import (
    add_answer,
    add_evidence,
    create_idea,
    delete_idea,
    edit_answer,
    evidence_for,
    get_idea,
    get_idea_by_token,
    list_ideas,
    set_shared,
    set_station,
    set_status,
)
from ideas.view import idea_view, summary

BOARDS = (
    ("kitchen", "In the kitchen", ("cooking", "parked")),
    ("served", "Served", ("served",)),
    ("binned", "Binned", ("binned",)),
)


class SessionOver(Exception):
    pass


class Flows:
    def __init__(self, connection, review, today):
        self.connection = connection
        self.review = review
        self.today = today

    def page(self, idea_id):
        """The idea page: the founder's own text always, review's side only if review answers."""
        idea = get_idea(self.connection, idea_id)
        evidence = evidence_for(self.connection, idea_id)
        try:
            state = self.review.state(idea_id, _ids(idea), evidence, idea["level"])
        except ReviewUnavailable:
            state = None
        pivot_from = get_idea(self.connection, idea["pivot_of"]) if idea["pivot_of"] else None
        return idea_view(idea, evidence, state, pivot_from)

    def boards(self, mine):
        """This browser's ideas on boards, plus ideas others shared; labels only if review answers."""
        listed = [idea for idea in list_ideas(self.connection) if idea["token"] in mine or idea["shared"]]
        notice = None
        labels = {}
        if listed:
            try:
                labels = self.review.summaries([{"id": idea["id"], "revision_ids": idea["branch_ids"]} for idea in listed])
            except ReviewUnavailable:
                notice = "Scores can't be loaded right now."

        def label_of(idea):
            found = labels.get(str(idea["id"]))
            return found["labels"][-1] if found else None

        return {
            "boards": [
                {
                    "key": key,
                    "title": title,
                    "ideas": [summary(i, label_of(i)) for i in listed if i["token"] in mine and i["status"] in statuses],
                }
                for key, title, statuses in BOARDS
            ],
            "cohort": [summary(i, label_of(i)) for i in listed if i["shared"] and i["token"] not in mine],
            "notice": notice,
        }

    def pitch(self, fields):
        pivot = get_idea_by_token(self.connection, fields["pivot"]) if fields.get("pivot") else None
        idea = create_idea(
            self.connection,
            fields.get("display_name"),
            fields.get("one_liner"),
            fields.get("story"),
            tone=fields.get("tone"),
            shared=bool(fields.get("shared")),
            pivot_of=pivot["id"] if pivot else None,
            consent=bool(fields.get("consent")),
            level=fields.get("level"),
        )
        self._play_if_possible(idea)
        return idea["id"]

    def answer(self, idea, text):
        """Review decides whether the session is still open, so an answer is only saved once it says so."""
        if self._state(idea)["step"] != "open":
            raise SessionOver()
        idea = add_answer(self.connection, idea["id"], text)
        self._play_if_possible(idea)
        return idea["id"]

    def edit(self, idea, revision_id, text):
        idea = edit_answer(self.connection, idea["id"], revision_id, text)
        self._play_if_possible(idea)
        return idea["id"]

    def retry(self, idea):
        self._play(idea)
        return idea["id"]

    def log_evidence(self, idea, fields):
        add_evidence(self.connection, idea["id"], self.review.sessions(idea["id"]), fields, today=self.today)
        if idea["station"] == "prep":
            set_station(self.connection, idea["id"], "tasting")
        return idea["id"]

    def search_facts(self, idea):
        kept = {entry["quote"] for entry in evidence_for(self.connection, idea["id"]) if entry["kind"] == "fact"}
        pitch = idea["branch"][0]
        found = self.review.facts(pitch["one_liner"], pitch["story"])
        fresh = [fact for fact in found["facts"] if fact["fact"] not in kept]
        notice = "Chef found nothing new. You already kept these facts." if found["facts"] and not fresh else None
        return {"facts": fresh, "searches": found.get("searches", []), "notice": notice}

    def keep_facts(self, idea, picked):
        """Facts from a search are stored only once the founder picks them."""
        session = self.review.sessions(idea["id"])
        for fact in picked:
            fields = {
                "kind": "fact",
                "quote": fact.get("quote", ""),
                "source": fact.get("source", ""),
                "who": fact.get("who", ""),
                "spoken_on": self.today.isoformat(),
            }
            add_evidence(self.connection, idea["id"], session, fields, today=self.today)
        return idea["id"]

    def gate(self, idea):
        if idea["status"] in CLOSED:
            raise IdeaClosed(idea["status"])
        result = self.review.gate(idea["id"], idea["branch"][-1]["id"], self._text(idea), idea["level"])
        if result["label"] == "PASSED":
            set_station(self.connection, idea["id"], "grill")
        return idea["id"]

    def serve(self, idea):
        if idea["status"] in CLOSED:
            return idea["id"]
        self.review.serve(_ids(idea), self._text(idea))
        set_status(self.connection, idea["id"], "served")
        set_station(self.connection, idea["id"], "takeaway")
        return idea["id"]

    def write_pack(self, idea):
        self.review.pack(_ids(idea), self._text(idea), idea["status"] == "served")
        return idea["id"]

    def starter_pack(self, idea):
        """The Markdown file, or None until review holds a pack. The evidence comes from ideas' own logs."""
        state = self._state(idea)
        stored = state["pack"]
        if stored is None:
            return None
        return render_pack(
            idea["branch"][0]["one_liner"],
            idea["display_name"],
            evidence_for(self.connection, idea["id"]),
            stored["body"],
            stored["body"]["verified"],
            stored["created_at"][:10],
            needed=state["serve_min_logs"],
        )

    def park(self, idea):
        try:
            set_status(self.connection, idea["id"], "parked")
        except IdeaClosed:
            pass
        return idea["id"]

    def share(self, idea):
        set_shared(self.connection, idea["id"], not idea["shared"])
        return idea["id"]

    def delete(self, idea):
        """Review forgets first: if it can't be reached, nothing is deleted, so no scores are left
        pointing at revisions that no longer exist."""
        self.review.forget(idea["id"], [revision["id"] for revision in idea["revisions"]])
        delete_idea(self.connection, idea["id"])

    def organizer(self):
        ideas = list_ideas(self.connection)
        found = self.review.summaries([{"id": idea["id"], "revision_ids": idea["branch_ids"]} for idea in ideas]) if ideas else {}
        for idea in ideas:
            idea["labels"] = found[str(idea["id"])]["labels"]
            idea["gates_passed"] = found[str(idea["id"])]["gates_passed"]
        table = rows(ideas, self.today)
        for row in table:
            row["station_name"] = station_name(row["station"])
        return {"rows": table, "metrics": metrics(ideas, self.today), "today": self.today.isoformat()}

    def _text(self, idea):
        return founder_text(idea["branch"], evidence_for(self.connection, idea["id"]))

    def _state(self, idea):
        return self.review.state(idea["id"], _ids(idea), evidence_for(self.connection, idea["id"]), idea["level"])

    def _play(self, idea):
        """The flow across the seam: review scores the newest revision and Chef answers it,
        then ideas moves the idea to the station review's step calls for."""
        result = self.review.round(idea["id"], _ids(idea), self._text(idea), idea["tone"], idea["level"])
        if result["step"] == "binned":
            set_status(self.connection, idea["id"], "binned")
        set_station(self.connection, idea["id"], "tasting" if result["step"] == "homework" else "grill")
        return result

    def _play_if_possible(self, idea):
        """A saved pitch or answer stays saved when review is down or slow; the page shows it as not scored yet."""
        try:
            self._play(idea)
        except ReviewUnavailable:
            pass


def _ids(idea):
    return [revision["id"] for revision in idea["branch"]]
