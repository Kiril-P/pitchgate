import hmac
import logging
from datetime import date

from flask import Response, abort, current_app, g, jsonify, request
from werkzeug.exceptions import BadRequest, HTTPException

from ideas.db import connect
from ideas.flows import Flows, SessionOver
from ideas.logic import IdeaClosed, IdeaNotFound, IdeaTextError
from ideas.review_client import ReviewRefused, ReviewUnavailable
from ideas.store import get_idea_by_token

log = logging.getLogger(__name__)

REQUEST_CONNECT_ATTEMPTS = 3

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


def register_api(app):
    def flows():
        return Flows(get_db(), app.config["REVIEW"], app.config.get("TODAY") or date.today())

    def load(token):
        idea = get_idea_by_token(get_db(), token)
        if idea is None:
            abort(404, "There is no idea at this link.")
        return idea

    def page(idea_id, status=200):
        return jsonify(flows().page(idea_id)), status

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

    @app.errorhandler(SessionOver)
    def session_over(_error):
        return refused(409, "This session is over. Log real conversations to open the next one.")

    @app.errorhandler(IdeaClosed)
    def closed(_error):
        return refused(409, CLOSED_MESSAGE)

    @app.errorhandler(IdeaNotFound)
    def not_on_this_idea(_error):
        return refused(404, "That answer isn't part of this idea.")

    @app.errorhandler(IdeaTextError)
    def bad_text(error):
        return refused(400, str(error), error.field)

    @app.errorhandler(Exception)
    def unexpected(_error):
        log.exception("unhandled error")
        return refused(500, "Something went wrong in the ideas service.")

    @app.get("/ideas")
    def boards():
        """This browser's ideas (tokens it keeps, passed as ?mine=a,b) on boards, plus ideas others shared."""
        mine = {token for token in request.args.get("mine", "").split(",") if token}
        return jsonify(flows().boards(mine))

    @app.post("/ideas")
    def create():
        return page(flows().pitch(body()), 201)

    @app.get("/ideas/<token>")
    def idea_detail(token):
        return page(load(token)["id"])

    @app.post("/ideas/<token>/answers")
    def answer(token):
        return page(flows().answer(load(token), body().get("answer")), 201)

    @app.post("/ideas/<token>/answers/<int:revision_id>")
    def edit(token, revision_id):
        return page(flows().edit(load(token), revision_id, body().get("answer")), 201)

    @app.post("/ideas/<token>/retry")
    def retry(token):
        return page(flows().retry(load(token)))

    @app.post("/ideas/<token>/evidence")
    def log_evidence(token):
        found = body()
        fields = {field: found.get(field, "") for field in EVIDENCE_FIELDS}
        return page(flows().log_evidence(load(token), fields), 201)

    @app.post("/ideas/<token>/facts/search")
    def search_facts(token):
        return jsonify(flows().search_facts(load(token)))

    @app.post("/ideas/<token>/facts")
    def keep_facts(token):
        picked = body().get("facts") or []
        idea = load(token)
        if not picked:
            return refused(400, "Tick at least one fact to keep.", "facts")
        return page(flows().keep_facts(idea, picked), 201)

    @app.post("/ideas/<token>/gate")
    def gate(token):
        return page(flows().gate(load(token)))

    @app.post("/ideas/<token>/serve")
    def serve(token):
        return page(flows().serve(load(token)))

    @app.post("/ideas/<token>/pack")
    def write_starter_pack(token):
        return page(flows().write_pack(load(token)))

    @app.get("/ideas/<token>/starter-pack.md")
    def starter_pack(token):
        text = flows().starter_pack(load(token))
        if text is None:
            abort(404, "Write the starter pack first.")
        return Response(text, mimetype="text/markdown", headers={"Content-Disposition": 'attachment; filename="starter-pack.md"'})

    @app.post("/ideas/<token>/park")
    def park(token):
        return page(flows().park(load(token)))

    @app.post("/ideas/<token>/share")
    def share(token):
        return page(flows().share(load(token)))

    @app.delete("/ideas/<token>")
    def delete(token):
        flows().delete(load(token))
        return "", 204

    @app.get("/organizer")
    def organizer():
        expected = app.config["ORGANIZER_KEY"]
        if not expected:
            abort(404)
        given = request.headers.get("X-Organizer-Key", "") or request.args.get("key", "")
        if not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
            return refused(403, "That organizer key is not right." if given else "This page needs the organizer key.")
        return jsonify(flows().organizer())
