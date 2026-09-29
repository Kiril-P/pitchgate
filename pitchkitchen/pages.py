from flask import abort, redirect, render_template, request, url_for

from pitchkitchen.db import connect
from pitchkitchen.ideas.logic import LIMITS, IdeaNotFound, IdeaTextError, founder_text
from pitchkitchen.ideas.store import (
    add_answer,
    create_idea,
    get_branch,
    get_idea,
    list_ideas,
)
from pitchkitchen.review.store import record_verdict, verdicts_for


def register_routes(app):
    def score(connection, branch):
        record_verdict(
            connection,
            branch[-1]["id"],
            founder_text(branch),
            app.config.get("TYPESAFE_API_KEY", ""),
        )

    def render_home(connection, error, form, status=200):
        ideas = list_ideas(connection)
        found = verdicts_for(connection, [idea["head_id"] for idea in ideas])
        for idea in ideas:
            idea["verdict"] = found.get(idea["head_id"])
        page = render_template("home.html", ideas=ideas, error=error, form=form, limits=LIMITS)
        return page, status

    def render_idea(connection, idea, error, status=200):
        found = verdicts_for(connection, [revision["id"] for revision in idea["branch"]])
        for revision in idea["branch"]:
            revision["verdict"] = found.get(revision["id"])
        page = render_template("idea.html", idea=idea, error=error, limits=LIMITS)
        return page, status

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
            score(connection, idea["branch"])
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=idea["id"]))

    @app.get("/ideas/<int:idea_id>")
    def idea_detail(idea_id):
        connection = connect(app.config["DATABASE"])
        try:
            idea = get_idea(connection, idea_id)
            if idea is None:
                abort(404)
            return render_idea(connection, idea, None)
        finally:
            connection.close()

    @app.post("/ideas/<int:idea_id>/answers")
    def answer(idea_id):
        connection = connect(app.config["DATABASE"])
        try:
            try:
                idea = add_answer(connection, idea_id, request.form.get("answer", ""))
            except IdeaNotFound:
                abort(404)
            except IdeaTextError as error:
                return render_idea(connection, get_idea(connection, idea_id), error.message, 400)
            score(connection, idea["branch"])
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
            score(connection, branch)
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=branch[0]["idea_id"]))


def _pitch_form(source=None):
    source = source or {}
    return {
        "display_name": source.get("display_name", ""),
        "one_liner": source.get("one_liner", ""),
        "story": source.get("story", ""),
    }
