import hmac
import logging
from datetime import date

from flask import Response, abort, current_app, g, jsonify, request
from werkzeug.exceptions import BadRequest, HTTPException

from ideas.cohort import metrics, rows
from ideas.db import connect
from ideas.logic import IdeaClosed, IdeaNotFound, IdeaTextError, founder_text, station_name
from ideas.pack import render_pack
from ideas.review_client import ReviewRefused, ReviewUnavailable
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

log = logging.getLogger(__name__)

REQUEST_CONNECT_ATTEMPTS = 3

BOARDS = (
    ("kitchen", "In the kitchen", ("cooking", "parked")),
    ("served", "Served", ("served",)),
    ("binned", "Binned", ("binned",)),
)

EVIDENCE_FIELDS = ("kind", "who", "role", "spoken_on", "today_they", "paid", "quote", "source")

CLOSED_MESSAGE = "This idea is closed."
REVIEW_DOWN_WRITE = "Chef and Jev can't be reached right now, so nothing was saved. Try again in a minute."


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_URL"], attempts=REQUEST_CONNECT_ATTEMPTS)
    return g.db


def body():
    found = request.get_json(silent=True)
    if found is None:
        return {}
    if not isinstance(found, dict):
        raise BadRequest("Send a JSON object.")
    return found


def refused(status, message, field=None):
    payload = {"error": message}
    if field:
        payload["field"] = field
    return jsonify(payload), status


def text_error(error):
    return refused(400, str(error), error.field)


def register_api(app):
    review = app.config["REVIEW"]

    def today():
        return app.config.get("TODAY") or date.today()

    def load(connection, token):
        idea = get_idea_by_token(connection, token)
        if idea is None:
            abort(404, "There is no idea at this link.")
        return idea

    def ids_of(idea):
        return [revision["id"] for revision in idea["branch"]]

    def text_of(connection, idea):
        return founder_text(idea["branch"], evidence_for(connection, idea["id"]))

    def play(connection, idea):
        """The flow across the seam: review scores the newest revision and Chef answers it,
        then ideas moves the idea to the station review's step calls for."""
        result = review.round(idea["id"], ids_of(idea), text_of(connection, idea), idea["tone"], idea["level"])
        if result["step"] == "binned":
            set_status(connection, idea["id"], "binned")
        set_station(connection, idea["id"], "tasting" if result["step"] == "homework" else "grill")
        return result

    def play_if_possible(connection, idea):
        """A saved pitch or answer stays saved when review is down; the page shows it as not scored yet."""
        try:
            play(connection, idea)
        except ReviewUnavailable:
            pass

    def state_of(connection, idea):
        return review.state(idea["id"], ids_of(idea), evidence_for(connection, idea["id"]), idea["level"])

    def view(connection, idea_id, status=200):
        idea = get_idea(connection, idea_id)
        evidence = evidence_for(connection, idea_id)
        try:
            state = review.state(idea_id, ids_of(idea), evidence, idea["level"])
        except ReviewUnavailable:
            state = None
        pivot_from = get_idea(connection, idea["pivot_of"]) if idea["pivot_of"] else None
        return jsonify(idea_view(idea, evidence, state, pivot_from)), status

    @app.teardown_appcontext
    def close_db(_error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.errorhandler(HTTPException)
    def http_error(error):
        return refused(error.code, error.description)

    @app.errorhandler(ReviewUnavailable)
    def review_down(_error):
        return refused(503, REVIEW_DOWN_WRITE)

    @app.errorhandler(ReviewRefused)
    def review_said_no(error):
        return refused(error.status, error.message)

    @app.errorhandler(IdeaClosed)
    def closed(_error):
        return refused(409, CLOSED_MESSAGE)

    @app.errorhandler(IdeaTextError)
    def bad_text(error):
        return text_error(error)

    @app.errorhandler(Exception)
    def unexpected(_error):
        log.exception("unhandled error")
        return refused(500, "Something went wrong in the ideas service.")

    @app.get("/ideas")
    def boards():
        """This browser's ideas (tokens it keeps, passed as ?mine=a,b) on boards, plus ideas others shared."""
        connection = get_db()
        mine = {token for token in request.args.get("mine", "").split(",") if token}
        listed = [idea for idea in list_ideas(connection) if idea["token"] in mine or idea["shared"]]
        notice = None
        labels = {}
        if listed:
            try:
                labels = review.summaries([{"id": idea["id"], "revision_ids": idea["branch_ids"]} for idea in listed])
            except ReviewUnavailable:
                notice = "Scores can't be loaded right now."

        def label_of(idea):
            found = labels.get(str(idea["id"]))
            return found["labels"][-1] if found else None

        return jsonify(
            boards=[
                {
                    "key": key,
                    "title": title,
                    "ideas": [summary(i, label_of(i)) for i in listed if i["token"] in mine and i["status"] in statuses],
                }
                for key, title, statuses in BOARDS
            ],
            cohort=[summary(i, label_of(i)) for i in listed if i["shared"] and i["token"] not in mine],
            notice=notice,
        )

    @app.post("/ideas")
    def create():
        found = body()
        connection = get_db()
        pivot = get_idea_by_token(connection, found["pivot"]) if found.get("pivot") else None
        idea = create_idea(
            connection,
            found.get("display_name"),
            found.get("one_liner"),
            found.get("story"),
            tone=found.get("tone"),
            shared=bool(found.get("shared")),
            pivot_of=pivot["id"] if pivot else None,
            consent=bool(found.get("consent")),
            level=found.get("level"),
        )
        play_if_possible(connection, idea)
        return view(connection, idea["id"], 201)

    @app.get("/ideas/<token>")
    def idea_detail(token):
        connection = get_db()
        return view(connection, load(connection, token)["id"])

    @app.post("/ideas/<token>/answers")
    def answer(token):
        connection = get_db()
        idea = load(connection, token)
        if state_of(connection, idea)["step"] != "open":
            return refused(409, "This session is over. Log real conversations to open the next one.")
        idea = add_answer(connection, idea["id"], body().get("answer"))
        play_if_possible(connection, idea)
        return view(connection, idea["id"], 201)

    @app.post("/ideas/<token>/answers/<int:revision_id>")
    def edit(token, revision_id):
        connection = get_db()
        idea = load(connection, token)
        try:
            idea = edit_answer(connection, idea["id"], revision_id, body().get("answer"))
        except IdeaNotFound:
            abort(404, "That answer isn't part of this idea.")
        play_if_possible(connection, idea)
        return view(connection, idea["id"], 201)

    @app.post("/ideas/<token>/retry")
    def retry(token):
        connection = get_db()
        idea = load(connection, token)
        play(connection, idea)
        return view(connection, idea["id"])

    @app.post("/ideas/<token>/evidence")
    def log_evidence(token):
        found = body()
        connection = get_db()
        idea = load(connection, token)
        add_evidence(
            connection,
            idea["id"],
            review.sessions(idea["id"]),
            {field: found.get(field, "") for field in EVIDENCE_FIELDS},
            today=today(),
        )
        if idea["station"] == "prep":
            set_station(connection, idea["id"], "tasting")
        return view(connection, idea["id"], 201)

    @app.post("/ideas/<token>/facts/search")
    def search_facts(token):
        connection = get_db()
        idea = load(connection, token)
        kept = {entry["quote"] for entry in evidence_for(connection, idea["id"]) if entry["kind"] == "fact"}
        pitch = idea["branch"][0]
        found = review.facts(pitch["one_liner"], pitch["story"])
        fresh = [fact for fact in found["facts"] if fact["fact"] not in kept]
        notice = "Chef found nothing new. You already kept these facts." if found["facts"] and not fresh else None
        return jsonify(facts=fresh, searches=found.get("searches", []), notice=notice)

    @app.post("/ideas/<token>/facts")
    def keep_facts(token):
        """Facts from a search are stored only once the founder picks them."""
        picked = body().get("facts") or []
        connection = get_db()
        idea = load(connection, token)
        if not picked:
            return refused(400, "Tick at least one fact to keep.", "facts")
        session = review.sessions(idea["id"])
        for fact in picked:
            fields = {
                "kind": "fact",
                "quote": fact.get("quote", ""),
                "source": fact.get("source", ""),
                "who": fact.get("who", ""),
                "spoken_on": today().isoformat(),
            }
            add_evidence(connection, idea["id"], session, fields, today=today())
        return view(connection, idea["id"], 201)

    @app.post("/ideas/<token>/gate")
    def gate(token):
        connection = get_db()
        idea = load(connection, token)
        if idea["status"] in ("served", "binned"):
            return refused(409, CLOSED_MESSAGE)
        result = review.gate(idea["id"], idea["branch"][-1]["id"], text_of(connection, idea), idea["level"])
        if result["label"] == "PASSED":
            set_station(connection, idea["id"], "grill")
        return view(connection, idea["id"])

    @app.post("/ideas/<token>/serve")
    def serve(token):
        connection = get_db()
        idea = load(connection, token)
        if idea["status"] in ("served", "binned"):
            return view(connection, idea["id"])
        review.serve(ids_of(idea), text_of(connection, idea))
        set_status(connection, idea["id"], "served")
        set_station(connection, idea["id"], "takeaway")
        return view(connection, idea["id"])

    @app.post("/ideas/<token>/pack")
    def write_starter_pack(token):
        connection = get_db()
        idea = load(connection, token)
        review.pack(ids_of(idea), text_of(connection, idea), idea["status"] == "served")
        return view(connection, idea["id"])

    @app.get("/ideas/<token>/starter-pack.md")
    def starter_pack(token):
        connection = get_db()
        idea = load(connection, token)
        state = state_of(connection, idea)
        stored = state["pack"]
        if stored is None:
            abort(404, "Write the starter pack first.")
        text = render_pack(
            idea["branch"][0]["one_liner"],
            idea["display_name"],
            evidence_for(connection, idea["id"]),
            stored["body"],
            stored["body"]["verified"],
            stored["created_at"][:10],
            needed=state["serve_min_logs"],
        )
        return Response(text, mimetype="text/markdown", headers={"Content-Disposition": 'attachment; filename="starter-pack.md"'})

    @app.post("/ideas/<token>/park")
    def park(token):
        connection = get_db()
        idea = load(connection, token)
        try:
            set_status(connection, idea["id"], "parked")
        except IdeaClosed:
            pass
        return view(connection, idea["id"])

    @app.post("/ideas/<token>/share")
    def share(token):
        connection = get_db()
        idea = load(connection, token)
        set_shared(connection, idea["id"], not idea["shared"])
        return view(connection, idea["id"])

    @app.delete("/ideas/<token>")
    def delete(token):
        """Review forgets first: if it can't be reached, nothing is deleted, so no scores are left
        pointing at revisions that no longer exist."""
        connection = get_db()
        idea = load(connection, token)
        review.forget(idea["id"], [revision["id"] for revision in idea["revisions"]])
        delete_idea(connection, idea["id"])
        return "", 204

    @app.get("/organizer")
    def organizer():
        expected = app.config["ORGANIZER_KEY"]
        if not expected:
            abort(404)
        given = request.headers.get("X-Organizer-Key", "") or request.args.get("key", "")
        if not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
            return refused(403, "That organizer key is not right." if given else "This page needs the organizer key.")
        connection = get_db()
        ideas = list_ideas(connection)
        found = review.summaries([{"id": idea["id"], "revision_ids": idea["branch_ids"]} for idea in ideas]) if ideas else {}
        for idea in ideas:
            idea["labels"] = found[str(idea["id"])]["labels"]
            idea["gates_passed"] = found[str(idea["id"])]["gates_passed"]
        table = rows(ideas, today())
        for row in table:
            row["station_name"] = station_name(row["station"])
        return jsonify(rows=table, metrics=metrics(ideas, today()), today=today().isoformat())
