from flask import abort, redirect, render_template, request, url_for

from pitchkitchen.db import connect
from pitchkitchen.ideas.logic import (
    LIMITS,
    IdeaClosed,
    IdeaNotFound,
    IdeaTextError,
    founder_text,
)
from pitchkitchen.ideas.store import (
    add_answer,
    create_idea,
    delete_idea,
    get_branch,
    get_idea,
    list_ideas,
    set_status,
)
from pitchkitchen.review.coach import ChefUnavailable
from pitchkitchen.review.logic import ANSWER_CAP
from pitchkitchen.review.service import NotServable, run_round, serve, step_for
from pitchkitchen.review.store import chef_for, forget, jev_calls_used, verdicts_for

BOARDS = (
    ("kitchen", "In the kitchen", ("cooking", "parked")),
    ("served", "Served", ("served",)),
    ("binned", "Binned", ("binned",)),
)


def register_routes(app):
    def settings():
        return {
            "jev_key": app.config.get("TYPESAFE_API_KEY", ""),
            "jev_budget": app.config["JEV_BUDGET_PER_IDEA"],
            "chef_key": app.config.get("COACH_API_KEY", ""),
            "chef_model": app.config["COACH_MODEL"],
            "chef_url": app.config["COACH_URL"],
        }

    def play(connection, branch):
        result = run_round(
            connection,
            [revision["id"] for revision in branch],
            founder_text(branch),
            settings(),
            jev_transport=app.config.get("JEV_TRANSPORT"),
            chef_transport=app.config.get("CHEF_TRANSPORT"),
            idea_id=branch[0]["idea_id"],
        )
        if result["step"] == "binned":
            set_status(connection, branch[0]["idea_id"], "binned")
        return result

    def render_home(connection, error, form, status=200):
        ideas = list_ideas(connection)
        found = verdicts_for(connection, [idea["head_id"] for idea in ideas])
        for idea in ideas:
            idea["verdict"] = found.get(idea["head_id"])
        boards = [
            {"key": key, "title": title, "ideas": [i for i in ideas if i["status"] in statuses]}
            for key, title, statuses in BOARDS
        ]
        page = render_template(
            "home.html", boards=boards, total=len(ideas), error=error, form=form, limits=LIMITS
        )
        return page, status

    def render_idea(connection, idea, error, status=200):
        ids = [revision["id"] for revision in idea["branch"]]
        found = verdicts_for(connection, ids)
        chef = chef_for(connection, ids)
        for revision in idea["branch"]:
            revision["verdict"] = found.get(revision["id"])
            revision["chef"] = chef.get(revision["id"], {}).get("turn")
        head = idea["branch"][-1]
        paused = None
        if head["verdict"] is None or head["verdict"]["label"] == "PENDING":
            paused = "jev"
        elif head["chef"] is None:
            paused = "chef"
        page = render_template(
            "idea.html",
            idea=idea,
            head=head,
            step=step_for(connection, ids),
            paused=paused,
            polished=chef.get(head["id"], {}).get("polished"),
            answers_left=ANSWER_CAP - (len(ids) - 1),
            jev_used=jev_calls_used(connection, idea["id"]),
            jev_budget=app.config["JEV_BUDGET_PER_IDEA"],
            error=error,
            limits=LIMITS,
        )
        return page, status

    def load(connection, idea_id):
        idea = get_idea(connection, idea_id)
        if idea is None:
            abort(404)
        return idea

    @app.get("/")
    def home():
        connection = connect(app.config["DATABASE"])
        try:
            return render_home(connection, None, _pitch_form())
        finally:
            connection.close()

    @app.post("/ideas")
    def create():
        form = _pitch_form(request.form)
        connection = connect(app.config["DATABASE"])
        try:
            try:
                idea = create_idea(
                    connection,
                    form["display_name"],
                    form["one_liner"],
                    form["story"],
                )
            except IdeaTextError as error:
                return render_home(connection, error.message, form, 400)
            play(connection, idea["branch"])
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=idea["id"]))

    @app.get("/ideas/<int:idea_id>")
    def idea_detail(idea_id):
        connection = connect(app.config["DATABASE"])
        try:
            return render_idea(connection, load(connection, idea_id), None)
        finally:
            connection.close()

    @app.post("/ideas/<int:idea_id>/answers")
    def answer(idea_id):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, idea_id)
            ids = [revision["id"] for revision in idea["branch"]]
            if step_for(connection, ids) != "open":
                return render_idea(connection, idea, "This interview is over. The last verdict stands.", 409)
            try:
                idea = add_answer(connection, idea_id, request.form.get("answer", ""))
            except IdeaClosed:
                return render_idea(connection, idea, "This idea is closed.", 409)
            except IdeaTextError as error:
                return render_idea(connection, idea, error.message, 400)
            play(connection, idea["branch"])
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=idea_id))

    @app.post("/revisions/<int:revision_id>/verdict")
    def score_revision(revision_id):
        connection = connect(app.config["DATABASE"])
        try:
            branch = get_branch(connection, revision_id)
            if branch is None:
                abort(404)
            play(connection, branch)
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=branch[0]["idea_id"]))

    @app.post("/ideas/<int:idea_id>/park")
    def park(idea_id):
        connection = connect(app.config["DATABASE"])
        try:
            load(connection, idea_id)
            try:
                set_status(connection, idea_id, "parked")
            except IdeaClosed:
                pass
        finally:
            connection.close()
        return redirect(url_for("home"))

    @app.post("/ideas/<int:idea_id>/delete")
    def delete(idea_id):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, idea_id)
            forget(connection, [revision["id"] for revision in idea["revisions"]])
            delete_idea(connection, idea_id)
        finally:
            connection.close()
        return redirect(url_for("home"))

    @app.post("/ideas/<int:idea_id>/serve")
    def serve_idea(idea_id):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, idea_id)
            if idea["status"] in ("served", "binned"):
                return redirect(url_for("idea_detail", idea_id=idea_id))
            branch = idea["branch"]
            try:
                serve(
                    connection,
                    [revision["id"] for revision in branch],
                    founder_text(branch),
                    settings(),
                    chef_transport=app.config.get("CHEF_TRANSPORT"),
                )
            except NotServable:
                return render_idea(connection, idea, "Only a SHIP can be saved as final.", 409)
            except ChefUnavailable:
                return render_idea(connection, idea, "Chef stepped out before writing your pitch. Try again.", 503)
            set_status(connection, idea_id, "served")
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=idea_id))


def _pitch_form(source=None):
    source = source or {}
    return {
        "display_name": source.get("display_name", ""),
        "one_liner": source.get("one_liner", ""),
        "story": source.get("story", ""),
    }
