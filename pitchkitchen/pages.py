from flask import abort, redirect, render_template, request, url_for

from pitchkitchen.db import connect
from pitchkitchen.ideas.logic import LIMITS, IdeaNotFound, IdeaTextError
from pitchkitchen.ideas.store import (
    create_idea,
    get_idea,
    get_revision,
    list_ideas,
    revise_idea,
)
from pitchkitchen.review.store import record_verdict, verdicts_for


def register_routes(app):
    @app.get("/")
    def home():
        connection = connect(app.config["DATABASE"])
        try:
            ideas = list_ideas(connection)
            _attach_latest_verdicts(connection, ideas)
        finally:
            connection.close()
        return render_template(
            "home.html",
            ideas=ideas,
            error=None,
            form=_blank_form(),
            limits=LIMITS,
        )

    @app.post("/ideas")
    def create():
        form = _read_form()
        connection = connect(app.config["DATABASE"])
        try:
            try:
                idea = create_idea(
                    connection,
                    form["display_name"],
                    form["problem"],
                    form["audience"],
                    form["approach"],
                )
            except IdeaTextError as error:
                ideas = list_ideas(connection)
                _attach_latest_verdicts(connection, ideas)
                return (
                    render_template(
                        "home.html",
                        ideas=ideas,
                        error=error.message,
                        form=form,
                        limits=LIMITS,
                    ),
                    400,
                )
            record_verdict(
                connection,
                idea["revisions"][0],
                app.config.get("TYPESAFE_API_KEY", ""),
            )
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=idea["id"]))

    @app.get("/ideas/<int:idea_id>")
    def idea_detail(idea_id):
        connection = connect(app.config["DATABASE"])
        try:
            idea = get_idea(connection, idea_id)
            if idea is not None:
                _attach_revision_verdicts(connection, idea)
        finally:
            connection.close()
        if idea is None:
            abort(404)
        return render_template(
            "idea.html",
            idea=idea,
            error=None,
            form=idea["revisions"][0],
            limits=LIMITS,
        )

    @app.post("/ideas/<int:idea_id>/revisions")
    def add_revision(idea_id):
        form = _read_form()
        connection = connect(app.config["DATABASE"])
        try:
            try:
                idea = revise_idea(
                    connection,
                    idea_id,
                    form["problem"],
                    form["audience"],
                    form["approach"],
                )
            except IdeaNotFound:
                abort(404)
            except IdeaTextError as error:
                idea = get_idea(connection, idea_id)
                _attach_revision_verdicts(connection, idea)
                return (
                    render_template(
                        "idea.html",
                        idea=idea,
                        error=error.message,
                        form=form,
                        limits=LIMITS,
                    ),
                    400,
                )
            record_verdict(
                connection,
                idea["revisions"][0],
                app.config.get("TYPESAFE_API_KEY", ""),
            )
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=idea_id))

    @app.post("/revisions/<int:revision_id>/verdict")
    def score_revision(revision_id):
        connection = connect(app.config["DATABASE"])
        try:
            revision = get_revision(connection, revision_id)
            if revision is None:
                abort(404)
            record_verdict(
                connection,
                revision,
                app.config.get("TYPESAFE_API_KEY", ""),
            )
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=revision["idea_id"]))


def _attach_latest_verdicts(connection, ideas):
    found = verdicts_for(connection, [idea["latest"]["id"] for idea in ideas])
    for idea in ideas:
        idea["verdict"] = found.get(idea["latest"]["id"])


def _attach_revision_verdicts(connection, idea):
    found = verdicts_for(
        connection,
        [revision["id"] for revision in idea["revisions"]],
    )
    for revision in idea["revisions"]:
        revision["verdict"] = found.get(revision["id"])


def _blank_form():
    return {
        "display_name": "",
        "problem": "",
        "audience": "",
        "approach": "",
    }


def _read_form():
    return {
        "display_name": request.form.get("display_name", ""),
        "problem": request.form.get("problem", ""),
        "audience": request.form.get("audience", ""),
        "approach": request.form.get("approach", ""),
    }
