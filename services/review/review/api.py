import logging

from flask import current_app, g, jsonify, request
from werkzeug.exceptions import BadRequest, HTTPException

from review.coach import ChefUnavailable, find_facts, suggest_one_liners, suggest_searches, suggest_sparks
from review.db import connect
from review.logic import SERVE_MIN_LOGS, SESSION_ANSWERS, STARTER_LEVELS, answers_left, can_serve, starter_gate
from review.service import (
    GateNotReady,
    NotServable,
    conversations,
    gate_status,
    run_gate,
    run_round,
    serve,
    sessions_for,
    step_for,
    write_pack,
)
from review.store import chef_for, forget, gates_passed, jev_calls_used, latest_homework, latest_of, verdicts_for

log = logging.getLogger(__name__)

REQUEST_CONNECT_ATTEMPTS = 3
TEXT_LIMIT = 2000


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_URL"], attempts=REQUEST_CONNECT_ATTEMPTS)
    return g.db


def body(*required):
    found = request.get_json(silent=True)
    if not isinstance(found, dict):
        raise BadRequest("Send a JSON object.")
    missing = [key for key in required if key not in found]
    if missing:
        raise BadRequest("Missing: " + ", ".join(missing) + ".")
    return found


def id_list(value, name="revision_ids"):
    if not isinstance(value, list) or not value or not all(isinstance(item, int) for item in value):
        raise BadRequest(name + " must be a non-empty list of integers.")
    return value


def keyed(found):
    """JSON object keys are strings, so revision ids go out as "12", not 12."""
    return {str(key): value for key, value in found.items()}


def refused(status, message):
    return jsonify(error=message), status


def register_api(app):
    def settings():
        return {
            "jev_key": app.config["TYPESAFE_API_KEY"],
            "jev_budget": app.config["JEV_BUDGET_PER_IDEA"],
            "chef_key": app.config["COACH_API_KEY"],
            "chef_model": app.config["COACH_MODEL"],
            "chef_url": app.config["COACH_URL"],
        }

    def chef_args():
        return (app.config["COACH_API_KEY"], app.config["COACH_MODEL"], app.config["COACH_URL"])

    @app.teardown_appcontext
    def close_db(_error):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    @app.errorhandler(HTTPException)
    def http_error(error):
        return refused(error.code, error.description)

    @app.errorhandler(Exception)
    def unexpected(error):
        log.exception("unhandled error")
        return refused(500, "Something went wrong in the review service.")

    @app.post("/rounds")
    def rounds():
        found = body("idea_id", "revision_ids", "founder_text")
        result = run_round(
            get_db(),
            id_list(found["revision_ids"]),
            found["founder_text"],
            settings(),
            jev_transport=app.config["JEV_TRANSPORT"],
            chef_transport=app.config["CHEF_TRANSPORT"],
            idea_id=found["idea_id"],
            tone=found.get("tone") or "tough",
            level=found.get("level") or "idea",
        )
        return jsonify(result)

    @app.post("/ideas/<int:idea_id>/state")
    def state(idea_id):
        """Everything review knows about one branch, plus the rules that depend on the founder's logs,
        which arrive in the body because they belong to the ideas service."""
        found = body("revision_ids")
        revision_ids = id_list(found["revision_ids"])
        evidence = found.get("evidence") or []
        level = found.get("level") or "idea"
        connection = get_db()
        sessions = sessions_for(connection, idea_id)
        verdicts = verdicts_for(connection, revision_ids)
        head = verdicts.get(revision_ids[-1])
        return jsonify(
            sessions=sessions,
            step=step_for(connection, revision_ids, sessions),
            verdicts=keyed(verdicts),
            chef=keyed(chef_for(connection, revision_ids)),
            homework=latest_homework(connection, revision_ids),
            pack=latest_of(connection, revision_ids, "starter_pack"),
            gate=gate_status(connection, idea_id, evidence),
            answers_left=answers_left(len(revision_ids) - 1, sessions),
            session_answers=SESSION_ANSWERS,
            servable=can_serve(head["label"] if head else "PENDING", len(conversations(evidence))),
            serve_min_logs=SERVE_MIN_LOGS,
            starter=level in STARTER_LEVELS,
            starter_gate=starter_gate(level, sessions),
            jev_used=jev_calls_used(connection, idea_id),
            jev_budget=app.config["JEV_BUDGET_PER_IDEA"],
        )

    @app.get("/ideas/<int:idea_id>/sessions")
    def sessions(idea_id):
        return jsonify(sessions=sessions_for(get_db(), idea_id))

    @app.delete("/ideas/<int:idea_id>")
    def forget_idea(idea_id):
        raw = request.args.get("revisions", "")
        try:
            revision_ids = [int(part) for part in raw.split(",") if part]
        except ValueError:
            raise BadRequest("revisions must be comma-separated integers.")
        forget(get_db(), idea_id, revision_ids)
        return "", 204

    @app.post("/summaries")
    def summaries():
        found = body("ideas")
        connection = get_db()
        wanted = [(item["id"], id_list(item["revision_ids"])) for item in found["ideas"]]
        verdicts = verdicts_for(connection, [rid for _, ids in wanted for rid in ids])
        return jsonify(
            ideas={
                str(idea_id): {
                    "labels": [verdicts[rid]["label"] if rid in verdicts else "PENDING" for rid in ids],
                    "gates_passed": gates_passed(connection, idea_id),
                }
                for idea_id, ids in wanted
            }
        )

    @app.post("/gates")
    def gates():
        found = body("idea_id", "head_id", "founder_text")
        connection = get_db()
        level = found.get("level") or "idea"
        try:
            gate = run_gate(
                connection,
                found["idea_id"],
                found["head_id"],
                found["founder_text"],
                settings(),
                jev_transport=app.config["JEV_TRANSPORT"],
                starter=starter_gate(level, sessions_for(connection, found["idea_id"])),
            )
        except GateNotReady:
            return refused(409, "Log at least 3 conversations this session, or a new one since the last try.")
        return jsonify(gate)

    @app.post("/serve")
    def serve_idea():
        found = body("revision_ids", "founder_text")
        try:
            served = serve(
                get_db(), id_list(found["revision_ids"]), found["founder_text"], settings(), chef_transport=app.config["CHEF_TRANSPORT"]
            )
        except NotServable:
            return refused(409, "Serving needs a PROVEN verdict and at least 3 logged conversations.")
        except ChefUnavailable:
            return refused(503, "Chef stepped out before writing your pitch. Try again.")
        return jsonify(served)

    @app.post("/packs")
    def packs():
        found = body("revision_ids", "founder_text", "verified")
        try:
            stored = write_pack(
                get_db(),
                id_list(found["revision_ids"]),
                found["founder_text"],
                settings(),
                bool(found["verified"]),
                chef_transport=app.config["CHEF_TRANSPORT"],
            )
        except ChefUnavailable:
            return refused(503, "Chef stepped out before writing your starter pack. Try again.")
        return jsonify(stored)

    @app.post("/suggestions/one-liners")
    def one_liners():
        rough = str(body("text")["text"]).strip()
        if not rough:
            return refused(400, "Write a rough idea or story first.")
        try:
            found = suggest_one_liners(rough[:TEXT_LIMIT], *chef_args(), transport=app.config["CHEF_TRANSPORT"])
        except ChefUnavailable:
            return refused(503, "Chef is busy. Try again in a moment.")
        return jsonify(suggestions=[{"one_liner": text} for text in found])

    @app.post("/suggestions/sparks")
    def sparks():
        about = str(body("about")["about"]).strip()
        if not about:
            return refused(400, "Tell Chef a little about your week first.")
        try:
            found = suggest_sparks(about[:TEXT_LIMIT], *chef_args(), transport=app.config["CHEF_TRANSPORT"])
        except ChefUnavailable:
            return refused(503, "Chef is busy. Try again in a moment.")
        return jsonify(suggestions=found)

    @app.post("/facts")
    def facts():
        found = body("one_liner", "story")
        key, model, url = chef_args()
        try:
            return jsonify(facts=find_facts(found["one_liner"], found["story"], key, model, transport=app.config["SEARCH_TRANSPORT"]))
        except ChefUnavailable:
            pass
        try:
            searches = suggest_searches(found["one_liner"], found["story"], key, model, url, transport=app.config["CHEF_TRANSPORT"])
        except ChefUnavailable:
            return refused(503, "Chef couldn't search the web or suggest searches right now. Try again later.")
        return jsonify(facts=[], searches=searches)
